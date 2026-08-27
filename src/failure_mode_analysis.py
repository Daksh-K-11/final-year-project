"""
Failure Mode Analysis and Stress-Testing Suite
Evaluates model robustness against:
1. Sensor noise and electrical distortion
2. Telemetry packet loss and burst missing values
3. Seasonal shift and meteorological inversion extremes
"""

import os
import json
from typing import Dict, Any, List
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import seaborn as sns
import torch

from src.dataset_generator import generate_campus_iot_dataset
from src.data_preprocessor import AirQualityPreprocessor
from src.models.lstm_model import AirQualityLSTM
from src.models.bilstm_model import AirQualityBiLSTMAttention
from src.models.transformer_model import AirQualityTransformer
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

def evaluate_sensor_noise_robustness(
    models_dict: Dict[str, torch.nn.Module],
    preprocessor: AirQualityPreprocessor,
    X_test_base: np.ndarray,
    y_test_actual: np.ndarray,
    noise_levels: List[float] = [0.0, 0.05, 0.10, 0.15, 0.25, 0.40, 0.60]
) -> Dict[str, Dict[str, list]]:
    """
    Stress-tests models by injecting varying degrees of Gaussian noise into sensor telemetry.
    """
    results = {m_name: {'noise_levels': noise_levels, 'rmse': [], 'r2': [], 'mae': []} for m_name in models_dict}
    
    for sigma in noise_levels:
        # Add noise to input test sequences
        if sigma > 0:
            noise = np.random.normal(0, sigma, X_test_base.shape).astype(np.float32)
            X_noisy = X_test_base + noise
        else:
            X_noisy = X_test_base.copy()
            
        for model_name, model in models_dict.items():
            model.eval()
            with torch.no_grad():
                inputs = torch.tensor(X_noisy, dtype=torch.float32)
                outputs = model(inputs)
                if isinstance(outputs, tuple):
                    outputs = outputs[0]
                preds_scaled = outputs.cpu().numpy().reshape(-1, 1)
                preds = preprocessor.inverse_transform_target(preds_scaled).flatten()
                
                mae = mean_absolute_error(y_test_actual, preds)
                rmse = np.sqrt(mean_squared_error(y_test_actual, preds))
                r2 = r2_score(y_test_actual, preds)
                
                results[model_name]['rmse'].append(round(float(rmse), 2))
                results[model_name]['r2'].append(round(float(r2), 4))
                results[model_name]['mae'].append(round(float(mae), 2))
                
    return results

def evaluate_missing_telemetry_stress(
    models_dict: Dict[str, torch.nn.Module],
    df_raw: pd.DataFrame,
    missing_rates: List[float] = [0.0, 0.05, 0.10, 0.20, 0.35, 0.50]
) -> Dict[str, Any]:
    """
    Tests data imputation pipeline and model performance under varying missing packet rates.
    """
    results = {'missing_rates': [int(r * 100) for r in missing_rates], 'models': {m: [] for m in models_dict}}
    
    for r in missing_rates:
        df_corrupted = df_raw.copy()
        if r > 0:
            cols = ['pm25', 'pm10', 'no2', 'so2', 'co', 'o3', 'temperature', 'humidity']
            for col in cols:
                mask = np.random.rand(len(df_corrupted)) < r
                df_corrupted.loc[mask, col] = np.nan
                
        # Run through preprocessor with imputation
        prep = AirQualityPreprocessor(sequence_length=24, forecast_horizon=1)
        X_s, y_s, _ = prep.fit_transform(df_corrupted)
        X_seq, y_seq = prep.create_sequences(X_s, y_s)
        
        # Test on last 15%
        split_idx = int(0.85 * len(X_seq))
        X_test = X_seq[split_idx:]
        y_test = y_seq[split_idx:]
        y_actual = prep.inverse_transform_target(y_test.reshape(-1, 1)).flatten()
        
        for model_name, model in models_dict.items():
            model.eval()
            with torch.no_grad():
                inputs = torch.tensor(X_test, dtype=torch.float32)
                outputs = model(inputs)
                if isinstance(outputs, tuple):
                    outputs = outputs[0]
                preds_scaled = outputs.cpu().numpy().reshape(-1, 1)
                preds = prep.inverse_transform_target(preds_scaled).flatten()
                rmse = np.sqrt(mean_squared_error(y_actual, preds))
                results['models'][model_name].append(round(float(rmse), 2))
                
    return results

def evaluate_seasonal_variations(
    models_dict: Dict[str, torch.nn.Module],
    preprocessor: AirQualityPreprocessor,
    df_raw: pd.DataFrame
) -> Dict[str, Dict[str, float]]:
    """
    Evaluates model performance across distinct atmospheric seasons:
    - Winter (Smog/Inversion: Dec-Feb)
    - Summer (Photochemical Ozone: Apr-Jun)
    - Monsoon (Rain Washout: Jul-Sep)
    - Post-Monsoon (Transition: Oct-Nov)
    """
    seasons = {
        'Winter (Inversion / High PM)': [12, 1, 2],
        'Summer (High Temp / O3)': [4, 5, 6],
        'Monsoon (Washout / Low PM)': [7, 8, 9],
        'Post-Monsoon (Transition)': [10, 11, 3]
    }
    
    season_metrics = {}
    
    for s_name, months in seasons.items():
        df_season = df_raw[df_raw['month'].isin(months)].copy().reset_index(drop=True)
        if len(df_season) < 50:
            continue
            
        X_s, y_s, _ = preprocessor.transform(df_season)
        X_seq, y_seq = preprocessor.create_sequences(X_s, y_s)
        
        if len(X_seq) == 0:
            continue
            
        y_act = preprocessor.inverse_transform_target(y_seq.reshape(-1, 1)).flatten()
        season_metrics[s_name] = {}
        
        for m_name, model in models_dict.items():
            model.eval()
            with torch.no_grad():
                inputs = torch.tensor(X_seq, dtype=torch.float32)
                outputs = model(inputs)
                if isinstance(outputs, tuple):
                    outputs = outputs[0]
                preds_scaled = outputs.cpu().numpy().reshape(-1, 1)
                preds = preprocessor.inverse_transform_target(preds_scaled).flatten()
                rmse = np.sqrt(mean_squared_error(y_act, preds))
                r2 = r2_score(y_act, preds)
                season_metrics[s_name][m_name] = {
                    'RMSE': round(float(rmse), 2),
                    'R2': round(float(r2), 4)
                }
                
    return season_metrics

def run_failure_mode_analysis_suite(
    data_path: str = "data/campus_air_quality_raw.csv",
    models_dir: str = "saved_models",
    results_dir: str = "results"
) -> Dict[str, Any]:
    """Runs complete stress-test suite and outputs figures."""
    os.makedirs(results_dir, exist_ok=True)
    print("\n=======================================================")
    print("      RUNNING FAILURE MODE & ROBUSTNESS STRESS SUITE   ")
    print("=======================================================")
    
    if not os.path.exists(data_path):
        from src.dataset_generator import save_default_datasets
        save_default_datasets()
        
    df_raw = pd.read_csv(data_path)
    
    # Preprocessor
    preprocessor = AirQualityPreprocessor(sequence_length=24, forecast_horizon=1)
    X_s, y_s, _ = preprocessor.fit_transform(df_raw)
    X_seq, y_seq = preprocessor.create_sequences(X_s, y_s)
    
    # Test partition
    val_end = int(0.85 * len(X_seq))
    X_test = X_seq[val_end:]
    y_test = y_seq[val_end:]
    y_test_actual = preprocessor.inverse_transform_target(y_test.reshape(-1, 1)).flatten()
    
    input_dim = X_seq.shape[2]
    
    # Load trained models
    models = {
        'LSTM': AirQualityLSTM(input_dim=input_dim, hidden_dim=64, num_layers=2),
        'BiLSTM-Attention': AirQualityBiLSTMAttention(input_dim=input_dim, hidden_dim=64, num_layers=2),
        'Transformer': AirQualityTransformer(input_dim=input_dim, d_model=64, nhead=4, num_layers=2)
    }
    
    for name, model in models.items():
        ckpt = os.path.join(models_dir, f"{name.lower().replace('-', '_')}_best.pt")
        if os.path.exists(ckpt):
            model.load_state_dict(torch.load(ckpt, map_location='cpu'))
        else:
            print(f"Warning: Checkpoint {ckpt} not found. Running initialized model.")
            
    # 1. Sensor Noise Stress Test
    print("[Stress Test 1] Evaluating Sensor Noise Perturbation...")
    noise_res = evaluate_sensor_noise_robustness(models, preprocessor, X_test, y_test_actual)
    
    # Plot Noise Stress
    plt.figure(figsize=(10, 5))
    palette = {'LSTM': '#1f77b4', 'BiLSTM-Attention': '#2ca02c', 'Transformer': '#9467bd'}
    for m_name, vals in noise_res.items():
        plt.plot(vals['noise_levels'], vals['rmse'], marker='o', linewidth=2.4, label=m_name, color=palette.get(m_name, '#333333'))
    plt.title("Sensor Noise Stress Analysis: Prediction RMSE vs Gaussian Noise Perturbation (σ)", fontsize=13, fontweight='bold')
    plt.xlabel("Injected Sensor Noise Standard Deviation (σ)", fontsize=11)
    plt.ylabel("Prediction RMSE (AQI Score)", fontsize=11)
    plt.grid(True, alpha=0.3)
    plt.legend(frameon=True)
    plt.tight_layout()
    plt.savefig(os.path.join(results_dir, "failure_mode_noise_stress.png"), dpi=300)
    plt.close()
    
    # 2. Missing Telemetry Stress Test
    print("[Stress Test 2] Evaluating Missing Packet Dropout Rates...")
    missing_res = evaluate_missing_telemetry_stress(models, df_raw)
    
    plt.figure(figsize=(10, 5))
    rates = missing_res['missing_rates']
    for m_name, rmses in missing_res['models'].items():
        plt.plot(rates, rmses, marker='s', linewidth=2.4, label=m_name, color=palette.get(m_name, '#333333'))
    plt.title("Missing Telemetry Stress Test: Forecast Error vs IoT Packet Loss Rate", fontsize=13, fontweight='bold')
    plt.xlabel("Simulated IoT Packet Loss / Missing Data Rate (%)", fontsize=11)
    plt.ylabel("Prediction RMSE (AQI Score)", fontsize=11)
    plt.grid(True, alpha=0.3)
    plt.legend(frameon=True)
    plt.tight_layout()
    plt.savefig(os.path.join(results_dir, "failure_mode_missing_telemetry.png"), dpi=300)
    plt.close()
    
    # 3. Seasonal Variations Analysis
    print("[Stress Test 3] Evaluating Cross-Seasonal Meteorological Variations...")
    seasonal_res = evaluate_seasonal_variations(models, preprocessor, df_raw)
    
    # Plot Seasonal Bar Chart
    seasons = list(seasonal_res.keys())
    m_list = list(models.keys())
    fig, ax = plt.subplots(figsize=(12, 6))
    x = np.arange(len(seasons))
    width = 0.25
    
    for i, m_name in enumerate(m_list):
        rmses = [seasonal_res[s][m_name]['RMSE'] for s in seasons]
        ax.bar(x + i*width, rmses, width=width, label=m_name, color=palette.get(m_name))
        
    ax.set_xticks(x + width)
    ax.set_xticklabels(seasons, fontsize=10, fontweight='bold')
    ax.set_ylabel("Prediction RMSE (AQI)", fontsize=11)
    ax.set_title("Model Generalization Across Atmospheric Seasons (Inversion vs Monsoon Washout)", fontsize=13, fontweight='bold')
    ax.legend(frameon=True)
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(os.path.join(results_dir, "failure_mode_seasonal_drift.png"), dpi=300)
    plt.close()
    
    # Save Full Failure Mode Report
    failure_report = {
        'sensor_noise_analysis': noise_res,
        'missing_telemetry_analysis': missing_res,
        'seasonal_variation_analysis': seasonal_res
    }
    with open(os.path.join(results_dir, "failure_mode_summary.json"), 'w') as f:
        json.dump(failure_report, f, indent=4)
        
    print(f"[Stress Suite] Failure mode analysis completed. Artifacts saved in {results_dir}\n")
    return failure_report

if __name__ == "__main__":
    run_failure_mode_analysis_suite()
