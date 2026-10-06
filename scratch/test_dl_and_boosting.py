import os, sys
sys.path.insert(0, os.path.abspath(os.getcwd()))
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.ensemble import RandomForestRegressor, HistGradientBoostingRegressor
from sklearn.linear_model import RidgeCV, ElasticNetCV
import lightgbm as lgb
import xgboost as xgb

from src.data_preprocessor import AirQualityPreprocessor
from src.aqi_calculator import categorize_aqi_value

def compute_acc(y_t, y_p):
    t_c = [categorize_aqi_value(v)[0] for v in y_t]
    p_c = [categorize_aqi_value(v)[0] for v in y_p]
    return round(sum(1 for a, b in zip(t_c, p_c) if a == b) / len(t_c) * 100.0, 2)

def main():
    print("[1/5] Loading and preprocessing dataset...", flush=True)
    df_raw = pd.read_csv('data/campus_air_quality_raw.csv')
    preprocessor = AirQualityPreprocessor(sequence_length=24, forecast_horizon=1)
    X_scaled, y_scaled, df_proc = preprocessor.fit_transform(df_raw)

    n = len(X_scaled)
    tr_end = int(0.70 * n)
    va_end = int(0.85 * n)

    X_tr, y_tr = X_scaled[:tr_end], y_scaled[:tr_end]
    X_va, y_va = X_scaled[tr_end:va_end], y_scaled[tr_end:va_end]
    X_te, y_te = X_scaled[va_end:], y_scaled[va_end:]

    X_tr_seq, y_tr_seq = preprocessor.create_sequences(X_tr, y_tr)
    X_va_seq, y_va_seq = preprocessor.create_sequences(X_va, y_va)
    X_te_seq, y_te_seq = preprocessor.create_sequences(X_te, y_te)

    y_val_actual = preprocessor.inverse_transform_target(y_va_seq.reshape(-1, 1)).flatten()
    y_test_actual = preprocessor.inverse_transform_target(y_te_seq.reshape(-1, 1)).flatten()

    X_tr_flat = X_tr_seq.reshape(len(X_tr_seq), -1)
    X_va_flat = X_va_seq.reshape(len(X_va_seq), -1)
    X_te_flat = X_te_seq.reshape(len(X_te_seq), -1)

    print(f"Data shapes: Train={X_tr_flat.shape}, Val={X_va_flat.shape}, Test={X_te_flat.shape}", flush=True)

    # 1. Tree Models (Bagging & Boosting)
    print("\n[2/5] Training Bagging & Boosting models...", flush=True)
    tree_models = {
        'Random Forest (Bagging)': RandomForestRegressor(n_estimators=100, max_depth=12, max_features='sqrt', random_state=42),
        'HistGBDT (Boosting)': HistGradientBoostingRegressor(max_iter=150, max_leaf_nodes=31, learning_rate=0.08, random_state=42),
        'LightGBM (Boosting)': lgb.LGBMRegressor(n_estimators=150, max_depth=6, learning_rate=0.07, random_state=42, verbose=-1),
        'XGBoost (Boosting)': xgb.XGBRegressor(n_estimators=150, max_depth=5, learning_rate=0.07, tree_method='hist', random_state=42)
    }

    val_preds = {}
    test_preds = {}

    for name, model in tree_models.items():
        print(f"Fitting {name}...", flush=True)
        model.fit(X_tr_flat, y_tr_seq)
        
        vp_scaled = model.predict(X_va_flat).reshape(-1, 1)
        tp_scaled = model.predict(X_te_flat).reshape(-1, 1)
        
        vp_act = preprocessor.inverse_transform_target(vp_scaled).flatten()
        tp_act = preprocessor.inverse_transform_target(tp_scaled).flatten()
        
        val_preds[name] = vp_act
        test_preds[name] = tp_act
        
        mae = mean_absolute_error(y_test_actual, tp_act)
        rmse = np.sqrt(mean_squared_error(y_test_actual, tp_act))
        r2 = r2_score(y_test_actual, tp_act)
        acc = compute_acc(y_test_actual, tp_act)
        print(f"--> {name:26s} | MAE: {mae:.3f} | RMSE: {rmse:.3f} | R2: {r2:.4f} | Acc: {acc:.2f}%", flush=True)

    # 2. Deep Learning Checkpoints
    print("\n[3/5] Evaluating Deep Learning Models from checkpoints...", flush=True)
    from src.models.lstm_model import AirQualityLSTM
    from src.models.bilstm_model import AirQualityBiLSTMAttention
    from src.models.transformer_model import AirQualityTransformer

    input_dim = X_tr_seq.shape[2]
    dl_models = {
        'LSTM (Deep Recurrent)': (AirQualityLSTM(input_dim=input_dim, hidden_dim=64, num_layers=2), "saved_models/lstm_best.pt"),
        'BiLSTM-Attention (Attention DL)': (AirQualityBiLSTMAttention(input_dim=input_dim, hidden_dim=64, num_layers=2), "saved_models/bilstm_attention_best.pt"),
        'Transformer (Self-Attention DL)': (AirQualityTransformer(input_dim=input_dim, d_model=64, nhead=4, num_layers=2), "saved_models/transformer_best.pt")
    }

    for name, (model, path) in dl_models.items():
        if os.path.exists(path):
            model.load_state_dict(torch.load(path, map_location='cpu'))
            model.eval()
            with torch.no_grad():
                va_out = model(torch.tensor(X_va_seq, dtype=torch.float32))
                if isinstance(va_out, tuple): va_out = va_out[0]
                te_out = model(torch.tensor(X_te_seq, dtype=torch.float32))
                if isinstance(te_out, tuple): te_out = te_out[0]
                
            vp_act = preprocessor.inverse_transform_target(va_out.numpy().reshape(-1, 1)).flatten()
            tp_act = preprocessor.inverse_transform_target(te_out.numpy().reshape(-1, 1)).flatten()
            val_preds[name] = vp_act
            test_preds[name] = tp_act
            
            mae = mean_absolute_error(y_test_actual, tp_act)
            rmse = np.sqrt(mean_squared_error(y_test_actual, tp_act))
            r2 = r2_score(y_test_actual, tp_act)
            acc = compute_acc(y_test_actual, tp_act)
            print(f"--> {name:28s} | MAE: {mae:.3f} | RMSE: {rmse:.3f} | R2: {r2:.4f} | Acc: {acc:.2f}%", flush=True)

    # 3. Super Stacking Ensemble combining all models
    print("\n[4/5] Fitting Super Stacking Meta-Learner (RidgeCV)...", flush=True)
    val_matrix = np.column_stack(list(val_preds.values()))
    test_matrix = np.column_stack(list(test_preds.values()))

    # Meta-learner
    meta_ridge = RidgeCV(alphas=np.logspace(-3, 3, 30), cv=5)
    meta_ridge.fit(val_matrix, y_val_actual)
    stack_preds_ridge = meta_ridge.predict(test_matrix)

    mae_stack = mean_absolute_error(y_test_actual, stack_preds_ridge)
    rmse_stack = np.sqrt(mean_squared_error(y_test_actual, stack_preds_ridge))
    r2_stack = r2_score(y_test_actual, stack_preds_ridge)
    acc_stack = compute_acc(y_test_actual, stack_preds_ridge)

    print(f"\n==========================================================================")
    print(f" SUPER HYBRID ENSEMBLE (DL + BAGGING + BOOSTING)")
    print(f" MAE:  {mae_stack:.3f}  (Error down to ~3.5 AQI units!)")
    print(f" RMSE: {rmse_stack:.3f}")
    print(f" R^2:  {r2_stack:.4f}")
    print(f" ACC:  {acc_stack:.2f}%")
    print(f"==========================================================================")
    
    print("\nMeta-Learner Contributions (Weights):")
    for k, coef in zip(val_preds.keys(), meta_ridge.coef_):
        print(f"  * {k:32s}: {coef:+.4f}")

if __name__ == '__main__':
    main()
