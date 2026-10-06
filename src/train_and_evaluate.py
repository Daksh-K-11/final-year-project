"""
Training, Model Evaluation, and Metric Benchmarking Suite
"""

import os
import json
import time
from typing import Dict, Any, Tuple
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import seaborn as sns

import torch
import torch.nn as nn
from torch.utils.data import TensorDataset, DataLoader
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

from src.dataset_generator import generate_campus_iot_dataset
from src.data_preprocessor import AirQualityPreprocessor
from src.models.lstm_model import AirQualityLSTM
from src.models.bilstm_model import AirQualityBiLSTMAttention
from src.models.transformer_model import AirQualityTransformer
from src.models.baselines import BaselineModels
from src.models.ensemble_model import AirQualityEnsemble
from src.aqi_calculator import categorize_aqi_value

# Set styling for publication quality figures
plt.style.use('seaborn-v0_8-whitegrid' if 'seaborn-v0_8-whitegrid' in plt.style.available else 'default')
plt.rcParams['font.family'] = 'sans-serif'
plt.rcParams['font.size'] = 11

def compute_aqi_classification_accuracy(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """
    Computes exact category classification accuracy based on standard CPCB AQI bands.
    """
    true_cats = [categorize_aqi_value(v)[0] for v in y_true]
    pred_cats = [categorize_aqi_value(v)[0] for v in y_pred]
    correct = sum(1 for t, p in zip(true_cats, pred_cats) if t == p)
    return round((correct / len(true_cats)) * 100.0, 2)

def compute_mape(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """Computes Mean Absolute Percentage Error (MAPE)."""
    y_true_safe = np.where(y_true == 0, 1e-5, y_true)
    return round(float(np.mean(np.abs((y_true - y_pred) / y_true_safe)) * 100.0), 2)

def train_torch_model(
    model: nn.Module,
    train_loader: DataLoader,
    val_loader: DataLoader,
    epochs: int = 35,
    lr: float = 0.001,
    weight_decay: float = 1e-4,
    device: str = "cpu"
) -> Tuple[nn.Module, Dict[str, list]]:
    """
    Standard PyTorch training loop with AdamW optimizer, cosine annealing scheduler,
    and MSE / Huber loss.
    """
    model.to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=weight_decay)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs)
    criterion = nn.SmoothL1Loss()  # Huber loss for robustness against sensor noise
    
    history = {'train_loss': [], 'val_loss': []}
    best_val_loss = float('inf')
    best_weights = None
    
    for epoch in range(epochs):
        # Training Phase
        model.train()
        train_loss = 0.0
        for X_batch, y_batch in train_loader:
            X_batch, y_batch = X_batch.to(device), y_batch.to(device)
            optimizer.zero_grad()
            
            outputs = model(X_batch)
            if isinstance(outputs, tuple):
                outputs = outputs[0]
                
            loss = criterion(outputs, y_batch)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
            optimizer.step()
            train_loss += loss.item() * len(X_batch)
            
        scheduler.step()
        train_loss /= len(train_loader.dataset)
        
        # Validation Phase
        model.eval()
        val_loss = 0.0
        with torch.no_grad():
            for X_batch, y_batch in val_loader:
                X_batch, y_batch = X_batch.to(device), y_batch.to(device)
                outputs = model(X_batch)
                if isinstance(outputs, tuple):
                    outputs = outputs[0]
                loss = criterion(outputs, y_batch)
                val_loss += loss.item() * len(X_batch)
                
        val_loss /= len(val_loader.dataset)
        
        history['train_loss'].append(train_loss)
        history['val_loss'].append(val_loss)
        
        if val_loss < best_val_loss:
            best_val_loss = val_loss
            best_weights = {k: v.cpu().clone() for k, v in model.state_dict().items()}
            
    if best_weights is not None:
        model.load_state_dict(best_weights)
        
    return model, history

def run_full_training_and_benchmarks(
    data_path: str = "data/campus_air_quality_raw.csv",
    results_dir: str = "results",
    models_dir: str = "saved_models",
    epochs: int = 35,
    skip_dl_training: bool = False
) -> Dict[str, Any]:
    """
    Executes full pipeline: load data -> preprocess -> train baselines, DL models & Hybrid Ensemble ->
    generate metrics & plots -> save artifacts.
    """
    os.makedirs(results_dir, exist_ok=True)
    os.makedirs(models_dir, exist_ok=True)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"[Training Engine] Running on device: {device}")
    
    # 1. Load or Generate Data
    if not os.path.exists(data_path):
        from src.dataset_generator import save_default_datasets
        save_default_datasets()
        
    df_raw = pd.read_csv(data_path)
    print(f"[Training Engine] Loaded dataset with {len(df_raw)} records.")
    
    # 2. Preprocess & Create Sequences
    preprocessor = AirQualityPreprocessor(sequence_length=24, forecast_horizon=1)
    X_scaled, y_scaled, df_processed = preprocessor.fit_transform(df_raw)
    
    # Train-Val-Test Split (Chronological 70% Train, 15% Val, 15% Test)
    n = len(X_scaled)
    train_end = int(0.70 * n)
    val_end = int(0.85 * n)
    
    X_tr, y_tr = X_scaled[:train_end], y_scaled[:train_end]
    X_va, y_va = X_scaled[train_end:val_end], y_scaled[train_end:val_end]
    X_te, y_te = X_scaled[val_end:], y_scaled[val_end:]
    
    # Slicing Sliding Windows
    X_tr_seq, y_tr_seq = preprocessor.create_sequences(X_tr, y_tr)
    X_va_seq, y_va_seq = preprocessor.create_sequences(X_va, y_va)
    X_te_seq, y_te_seq = preprocessor.create_sequences(X_te, y_te)
    
    y_test_actual = preprocessor.inverse_transform_target(y_te_seq.reshape(-1, 1)).flatten()
    
    # PyTorch DataLoaders
    batch_size = 64
    train_ds = TensorDataset(torch.tensor(X_tr_seq, dtype=torch.float32), torch.tensor(y_tr_seq, dtype=torch.float32))
    val_ds = TensorDataset(torch.tensor(X_va_seq, dtype=torch.float32), torch.tensor(y_va_seq, dtype=torch.float32))
    test_ds = TensorDataset(torch.tensor(X_te_seq, dtype=torch.float32), torch.tensor(y_te_seq, dtype=torch.float32))
    
    train_loader = DataLoader(train_ds, batch_size=batch_size, shuffle=True)
    val_loader = DataLoader(val_ds, batch_size=batch_size, shuffle=False)
    test_loader = DataLoader(test_ds, batch_size=batch_size, shuffle=False)
    
    input_dim = X_tr_seq.shape[2]
    all_metrics = {}
    predictions_dict = {'Ground_Truth': y_test_actual.tolist()}
    histories = {}
    
    # 3. Train Baselines
    print("\n--- Training Baseline Statistical Models ---")
    baselines = BaselineModels()
    base_res = baselines.fit_and_evaluate(X_tr_seq, y_tr_seq, X_te_seq, y_te_seq)
    
    for name, res in base_res.items():
        preds_scaled = res['predictions'].reshape(-1, 1)
        preds_actual = preprocessor.inverse_transform_target(preds_scaled).flatten()
        mae = mean_absolute_error(y_test_actual, preds_actual)
        rmse = np.sqrt(mean_squared_error(y_test_actual, preds_actual))
        r2 = r2_score(y_test_actual, preds_actual)
        mape = compute_mape(y_test_actual, preds_actual)
        acc = compute_aqi_classification_accuracy(y_test_actual, preds_actual)
        
        all_metrics[name] = {
            'MAE': round(float(mae), 3),
            'RMSE': round(float(rmse), 3),
            'R2_Score': round(float(r2), 4),
            'MAPE': mape,
            'AQI_Category_Accuracy': acc
        }
        predictions_dict[name] = preds_actual.tolist()
        print(f"[{name}] MAE: {mae:.2f} | RMSE: {rmse:.2f} | R2: {r2:.4f} | Acc: {acc:.1f}%")

    # 4. Train Deep Learning Models
    dl_models = {
        'LSTM': AirQualityLSTM(input_dim=input_dim, hidden_dim=64, num_layers=2),
        'BiLSTM-Attention': AirQualityBiLSTMAttention(input_dim=input_dim, hidden_dim=64, num_layers=2),
        'Transformer': AirQualityTransformer(input_dim=input_dim, d_model=64, nhead=4, num_layers=2)
    }
    
    attention_weights_sample = None
    
    for model_name, model in dl_models.items():
        ckpt_path = os.path.join(models_dir, f"{model_name.lower().replace('-', '_')}_best.pt")
        
        if skip_dl_training and os.path.exists(ckpt_path):
            print(f"\n--- Loading Checkpoint for {model_name} from {ckpt_path} ---")
            model.load_state_dict(torch.load(ckpt_path, map_location=device))
            trained_model = model.to(device)
            train_duration = 0.0
        else:
            print(f"\n--- Training {model_name} ({epochs} epochs) ---")
            start_t = time.time()
            trained_model, history = train_torch_model(model, train_loader, val_loader, epochs=epochs, device=device)
            train_duration = round(time.time() - start_t, 2)
            histories[model_name] = history
            
            # Save model checkpoint
            torch.save(trained_model.state_dict(), ckpt_path)
        
        # Predict on Test Set
        trained_model.eval()
        test_preds = []
        with torch.no_grad():
            for X_batch, _ in test_loader:
                X_batch = X_batch.to(device)
                out = trained_model(X_batch)
                if isinstance(out, tuple):
                    out, attns = out
                    if attention_weights_sample is None:
                        attention_weights_sample = attns.cpu().numpy()
                test_preds.extend(out.cpu().numpy().tolist())
                
        preds_scaled = np.array(test_preds).reshape(-1, 1)
        preds_actual = preprocessor.inverse_transform_target(preds_scaled).flatten()
        
        mae = mean_absolute_error(y_test_actual, preds_actual)
        rmse = np.sqrt(mean_squared_error(y_test_actual, preds_actual))
        r2 = r2_score(y_test_actual, preds_actual)
        mape = compute_mape(y_test_actual, preds_actual)
        acc = compute_aqi_classification_accuracy(y_test_actual, preds_actual)
        
        all_metrics[model_name] = {
            'MAE': round(float(mae), 3),
            'RMSE': round(float(rmse), 3),
            'R2_Score': round(float(r2), 4),
            'MAPE': mape,
            'AQI_Category_Accuracy': acc,
            'Train_Time_Sec': train_duration
        }
        predictions_dict[model_name] = preds_actual.tolist()
        print(f"[{model_name}] MAE: {mae:.2f} | RMSE: {rmse:.2f} | R2: {r2:.4f} | MAPE: {mape:.2f}% | Acc: {acc:.1f}%")

    # 5. Build, Fit, and Benchmark Hybrid Multi-Model Ensemble
    print("\n--- Fitting Hybrid Multi-Model Ensemble (Stacking & Adaptive Blending) ---")
    ensemble = AirQualityEnsemble(input_dim=input_dim)
    ensemble.bilstm = dl_models['BiLSTM-Attention']
    ensemble.transformer = dl_models['Transformer']
    ensemble.lstm = dl_models['LSTM']
    ensemble.set_rf_model(baselines.rf_model)
    boosting_model = getattr(baselines, 'xgb_model', None) or getattr(baselines, 'hgb_model', None)
    if boosting_model is not None:
        ensemble.set_boosting_model(boosting_model)
    
    # Fit meta-learner and optimal weights on validation sequence split
    opt_weights = ensemble.fit_meta_learner(X_va_seq, y_va_seq, device=device)
    print(f"[Ensemble Optimizer] Learned Optimal Convex Weights: {opt_weights}")
    
    # Save ensemble configuration and metadata
    ensemble_cfg_path = os.path.join(models_dir, "ensemble_config.json")
    ensemble.save(ensemble_cfg_path)

    
    # Predict on test set using Stacking Meta-Learner
    ens_preds_scaled, ens_meta = ensemble.predict(
        torch.tensor(X_te_seq, dtype=torch.float32),
        mode="stacking",
        device=device
    )
    ens_preds_actual = preprocessor.inverse_transform_target(ens_preds_scaled.reshape(-1, 1)).flatten()
    
    mae_ens = mean_absolute_error(y_test_actual, ens_preds_actual)
    rmse_ens = np.sqrt(mean_squared_error(y_test_actual, ens_preds_actual))
    r2_ens = r2_score(y_test_actual, ens_preds_actual)
    mape_ens = compute_mape(y_test_actual, ens_preds_actual)
    acc_ens = compute_aqi_classification_accuracy(y_test_actual, ens_preds_actual)
    
    all_metrics['Hybrid Ensemble'] = {
        'MAE': round(float(mae_ens), 3),
        'RMSE': round(float(rmse_ens), 3),
        'R2_Score': round(float(r2_ens), 4),
        'MAPE': mape_ens,
        'AQI_Category_Accuracy': acc_ens,
        'Weights': opt_weights,
        'Ensemble_Type': 'Stacking Meta-Learner (RidgeCV) + Convex Blending'
    }
    predictions_dict['Hybrid Ensemble'] = ens_preds_actual.tolist()
    print(f"[Hybrid Ensemble] MAE: {mae_ens:.2f} | RMSE: {rmse_ens:.2f} | R2: {r2_ens:.4f} | MAPE: {mape_ens:.2f}% | Acc: {acc_ens:.1f}%")

    # 6. Save Metrics Summary & Sample Predictions
    summary_path = os.path.join(results_dir, "metrics_summary.json")
    with open(summary_path, 'w') as f:
        json.dump(all_metrics, f, indent=4)
        
    preds_sample_path = os.path.join(results_dir, "test_predictions_sample.json")
    with open(preds_sample_path, 'w') as f:
        sample_out = {k: v[:200] for k, v in predictions_dict.items()}
        json.dump(sample_out, f, indent=4)

    # 7. Generate Figures & Academic Charts
    generate_all_plots(histories, predictions_dict, all_metrics, attention_weights_sample, results_dir, opt_weights)
    
    print(f"\n[Training Engine] Training and benchmark suite completed successfully.")
    print(f"Results, model checkpoints, and charts saved to: {results_dir}")
    return all_metrics

def generate_all_plots(histories, predictions_dict, all_metrics, attention_weights, results_dir, opt_weights=None):
    """Generates publication-quality figures for First Review report, paper, and slides."""
    
    # 1. Training and Validation Loss Curves
    fig, axes = plt.subplots(1, 3, figsize=(18, 5))
    model_names = ['LSTM', 'BiLSTM-Attention', 'Transformer']
    colors = ['#2b5c8f', '#2ca02c', '#d62728']
    
    for i, name in enumerate(model_names):
        if name in histories:
            ax = axes[i]
            epochs_range = range(1, len(histories[name]['train_loss']) + 1)
            ax.plot(epochs_range, histories[name]['train_loss'], label='Train Loss', color=colors[i], linewidth=2.2)
            ax.plot(epochs_range, histories[name]['val_loss'], label='Val Loss', color='#ff7f0e', linestyle='--', linewidth=2.0)
            ax.set_title(f"{name} Learning Convergence", fontsize=13, fontweight='bold')
            ax.set_xlabel("Epochs", fontsize=11)
            ax.set_ylabel("Huber Loss", fontsize=11)
            ax.legend(frameon=True)
            ax.grid(True, alpha=0.3)
            
    plt.tight_layout()
    plt.savefig(os.path.join(results_dir, "training_validation_loss.png"), dpi=300)
    plt.close()
    
    # 2. Prediction vs Actual Trajectory (Zoomed 120-hour window)
    plt.figure(figsize=(15, 6))
    window = 120
    gt = predictions_dict['Ground_Truth'][:window]
    plt.plot(gt, label='Actual AQI (Ground Truth)', color='#111111', linewidth=2.8, zorder=5)
    
    model_plot_styles = {
        'Random Forest': ('#ff7f0e', '--', 1.8),
        'HistGBDT (Boosting)': ('#0ea5e9', '--', 1.8),
        'XGBoost (Boosting)': ('#8b5cf6', ':', 1.8),
        'LSTM': ('#1f77b4', '-.', 2.0),
        'Transformer': ('#9467bd', '--', 2.0),
        'BiLSTM-Attention': ('#2ca02c', '-', 2.2),
        'Hybrid Ensemble': ('#e11d48', '-', 2.8)
    }
    
    for model_name, (col, ls, lw) in model_plot_styles.items():
        if model_name in predictions_dict:
            z_order = 6 if model_name == 'Hybrid Ensemble' else 3
            plt.plot(predictions_dict[model_name][:window], label=model_name, color=col, linestyle=ls, linewidth=lw, zorder=z_order)
            
    # Add AQI severity background shading
    plt.axhspan(0, 50, color='#00E400', alpha=0.08, label='Good (0-50)')
    plt.axhspan(51, 100, color='#FFFF00', alpha=0.08, label='Satisfactory (51-100)')
    plt.axhspan(101, 200, color='#FF7E00', alpha=0.08, label='Moderate (101-200)')
    plt.axhspan(201, 300, color='#FF0000', alpha=0.08, label='Poor (201-300)')
    
    plt.title("Multi-Model Air Quality Index (AQI) Forecasting vs Ground Truth (120-Hour Horizon)", fontsize=14, fontweight='bold')
    plt.xlabel("Time Horizon (Hours)", fontsize=12)
    plt.ylabel("Air Quality Index (AQI)", fontsize=12)
    plt.legend(loc='upper right', bbox_to_anchor=(1.20, 1.02), frameon=True, fontsize=10)
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(os.path.join(results_dir, "predictions_vs_actual.png"), dpi=300)
    plt.close()
    
    # 3. Model Metrics Comparative Bar Chart
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 6))
    models = list(all_metrics.keys())
    maes = [all_metrics[m]['MAE'] for m in models]
    rmses = [all_metrics[m]['RMSE'] for m in models]
    r2s = [all_metrics[m]['R2_Score'] for m in models]
    accs = [all_metrics[m]['AQI_Category_Accuracy'] for m in models]
    
    x = np.arange(len(models))
    w = 0.35
    
    # Error metrics (lower is better)
    b1 = ax1.bar(x - w/2, maes, width=w, label='MAE (Lower Better)', color='#4c72b0')
    b2 = ax1.bar(x + w/2, rmses, width=w, label='RMSE (Lower Better)', color='#c44e52')
    ax1.set_xticks(x)
    ax1.set_xticklabels(models, rotation=20, ha='right', fontweight='bold')
    ax1.set_ylabel("Error Score (AQI Points)", fontsize=12)
    ax1.set_title("Forecast Error Metrics (MAE vs RMSE)", fontsize=13, fontweight='bold')
    ax1.legend(frameon=True)
    ax1.grid(True, alpha=0.3)
    
    # Accuracy & R2 Score (higher is better)
    ax2.plot(models, r2s, marker='o', color='#55a868', linewidth=2.5, markersize=8, label='R² Score (0-1.0)')
    ax2_twin = ax2.twinx()
    ax2_twin.bar(x, accs, width=0.4, color='#8172b3', alpha=0.4, label='Category Accuracy (%)')
    ax2.set_xticks(x)
    ax2.set_xticklabels(models, rotation=20, ha='right', fontweight='bold')
    ax2.set_ylabel("R² Goodness of Fit Score", color='#55a868', fontsize=12)
    ax2_twin.set_ylabel("AQI Category Accuracy (%)", color='#8172b3', fontsize=12)
    ax2.set_title("Model Fit (R²) and AQI Level Classification Accuracy", fontsize=13, fontweight='bold')
    ax2.grid(True, alpha=0.3)
    
    plt.tight_layout()
    plt.savefig(os.path.join(results_dir, "model_metrics_comparison.png"), dpi=300)
    plt.close()
    
    # 4. Temporal Attention Heatmap
    if attention_weights is not None:
        plt.figure(figsize=(12, 5))
        attn_avg = np.mean(attention_weights[:20, :, 0], axis=0)
        time_steps = [f"t - {24 - i}h" for i in range(24)]
        
        sns.barplot(x=time_steps, y=attn_avg, palette="crest")
        plt.xticks(rotation=60, ha='right', fontsize=9)
        plt.title("BiLSTM Temporal Attention Weight Distribution Across 24-Hour Lookback Window", fontsize=13, fontweight='bold')
        plt.xlabel("Historical Time Step Lag", fontsize=11)
        plt.ylabel("Normalized Attention Weight", fontsize=11)
        plt.tight_layout()
        plt.savefig(os.path.join(results_dir, "attention_heatmap.png"), dpi=300)
        plt.close()

    # 5. Hybrid Ensemble Weights & Variance Reduction Breakdown
    if opt_weights is not None:
        fig, (e_ax1, e_ax2) = plt.subplots(1, 2, figsize=(15, 5))
        
        # Left: Optimal Convex Combination Allocation
        keys = list(opt_weights.keys())
        w_vals = [opt_weights[k] * 100.0 for k in keys]
        colors_pie = ['#2ca02c', '#9467bd', '#1f77b4', '#ff7f0e', '#0ea5e9', '#8b5cf6']
        
        bars = e_ax1.bar(keys, w_vals, color=colors_pie[:len(keys)], edgecolor='black', linewidth=1.2, width=0.5)
        for bar in bars:
            h = bar.get_height()
            e_ax1.text(bar.get_x() + bar.get_width() / 2., h + 1.0, f'{h:.1f}%', ha='center', va='bottom', fontweight='bold')
        e_ax1.set_ylim(0, max(w_vals) + 15)
        e_ax1.set_title("Optimal Ensemble Weight Contribution (%)", fontsize=13, fontweight='bold')
        e_ax1.set_ylabel("Normalized Convex Weight (%)", fontsize=11)
        e_ax1.grid(True, alpha=0.3)
        
        # Right: MAE Comparison showing Ensemble Superiority
        comp_models = [m for m in ['Random Forest', 'HistGBDT (Boosting)', 'XGBoost (Boosting)', 'LSTM', 'Transformer', 'BiLSTM-Attention', 'Hybrid Ensemble'] if m in all_metrics]
        comp_maes = [all_metrics[m]['MAE'] for m in comp_models]
        comp_colors = ['#ff7f0e', '#0ea5e9', '#8b5cf6', '#1f77b4', '#9467bd', '#2ca02c', '#e11d48']
        
        b_mae = e_ax2.barh(comp_models, comp_maes, color=comp_colors[:len(comp_models)], edgecolor='black', linewidth=1.1)
        for bar in b_mae:
            w_val = bar.get_width()
            e_ax2.text(w_val + 0.2, bar.get_y() + bar.get_height() / 2., f'{w_val:.2f}', ha='left', va='center', fontweight='bold')
        e_ax2.set_xlim(0, max(comp_maes) + 2.5)
        e_ax2.set_title("Mean Absolute Error (MAE) Comparison — Ensemble vs Individual Models", fontsize=13, fontweight='bold')
        e_ax2.set_xlabel("MAE (Lower is Better)", fontsize=11)
        e_ax2.grid(True, alpha=0.3)
        
        plt.tight_layout()
        plt.savefig(os.path.join(results_dir, "ensemble_weights_distribution.png"), dpi=300)
        plt.close()

if __name__ == "__main__":
    run_full_training_and_benchmarks()
