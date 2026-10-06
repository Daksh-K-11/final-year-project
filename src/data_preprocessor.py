"""
Data Preprocessing, Imputation, Feature Engineering, and Sequence Slicing Module
"""

import os
import json
from typing import Tuple, List, Dict, Any, Optional
import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler, MinMaxScaler
from src.aqi_calculator import calculate_overall_aqi

FEATURE_COLUMNS = [
    'aqi', 'aqi_rolling_mean_3h', 'aqi_rolling_mean_24h', 'aqi_diff_1h',
    'pm25', 'pm10', 'no2', 'so2', 'co', 'o3',
    'temperature', 'humidity', 'wind_speed',
    'hour_sin', 'hour_cos', 'month_sin', 'month_cos', 'dow_sin', 'dow_cos',
    'pm25_rolling_mean_3h', 'pm25_rolling_mean_24h', 'pm10_rolling_mean_3h',
    'pm25_diff_1h', 'temp_humidity_interaction', 'ventilation_index', 'pm_ratio'
]

TARGET_COLUMN = 'aqi'

class AirQualityPreprocessor:
    """
    Handles robust time-series preprocessing, imputation, cyclical encoding,
    feature engineering, and PyTorch dataset slicing.
    """
    def __init__(self, sequence_length: int = 24, forecast_horizon: int = 1):
        self.sequence_length = sequence_length
        self.forecast_horizon = forecast_horizon
        self.feature_scaler = StandardScaler()
        self.target_scaler = StandardScaler()
        self.is_fitted = False
        self.feature_names: List[str] = []
        
    def handle_missing_values(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Applies time-series linear interpolation followed by forward/backward fill.
        """
        df_clean = df.copy()
        numeric_cols = df_clean.select_dtypes(include=[np.number]).columns
        
        # Sort by timestamp if present
        if 'timestamp' in df_clean.columns:
            df_clean['timestamp'] = pd.to_datetime(df_clean['timestamp'])
            df_clean = df_clean.sort_values('timestamp').reset_index(drop=True)
            
        # Interpolate linear time series
        df_clean[numeric_cols] = df_clean[numeric_cols].interpolate(method='linear', limit_direction='both')
        df_clean[numeric_cols] = df_clean[numeric_cols].bfill().ffill()
        
        return df_clean

    def handle_outliers(self, df: pd.DataFrame, factor: float = 3.5) -> pd.DataFrame:
        """
        Clips extreme sensor glitches exceeding IQR threshold without losing physical trend.
        """
        df_out = df.copy()
        pollutants = ['pm25', 'pm10', 'no2', 'so2', 'co', 'o3']
        for col in pollutants:
            if col in df_out.columns:
                q25 = df_out[col].quantile(0.01)
                q99 = df_out[col].quantile(0.995)
                df_out[col] = df_out[col].clip(lower=max(0.0, q25), upper=q99 * 1.5)
        return df_out

    def engineer_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Derives temporal cyclical features, rolling statistics, and domain interactions.
        """
        df_feat = df.copy()
        
        # If AQI not in dataframe (e.g. streaming telemetry), compute instantaneous AQI
        if 'aqi' not in df_feat.columns:
            calc_aqis = []
            for _, row in df_feat.iterrows():
                pols = {
                    'PM2.5': row.get('pm25', 40.0),
                    'PM10': row.get('pm10', 80.0),
                    'NO2': row.get('no2', 30.0),
                    'SO2': row.get('so2', 12.0),
                    'CO': row.get('co', 1.0),
                    'O3': row.get('o3', 35.0)
                }
                calc_aqis.append(calculate_overall_aqi(pols)[0])
            df_feat['aqi'] = calc_aqis
        
        # Autoregressive historical AQI trends
        df_feat['aqi_rolling_mean_3h'] = df_feat['aqi'].rolling(window=3, min_periods=1).mean()
        df_feat['aqi_rolling_mean_24h'] = df_feat['aqi'].rolling(window=24, min_periods=1).mean()
        df_feat['aqi_diff_1h'] = df_feat['aqi'].diff().fillna(0)
        
        if 'timestamp' in df_feat.columns:
            ts = pd.to_datetime(df_feat['timestamp'])
            hour = ts.dt.hour
            month = ts.dt.month
            dow = ts.dt.dayofweek
        else:
            hour = df_feat['hour']
            month = df_feat['month']
            dow = df_feat['day_of_week']
            
        # Cyclical Temporal Encodings
        df_feat['hour_sin'] = np.sin(2 * np.pi * hour / 24.0)
        df_feat['hour_cos'] = np.cos(2 * np.pi * hour / 24.0)
        df_feat['month_sin'] = np.sin(2 * np.pi * month / 12.0)
        df_feat['month_cos'] = np.cos(2 * np.pi * month / 12.0)
        df_feat['dow_sin'] = np.sin(2 * np.pi * dow / 7.0)
        df_feat['dow_cos'] = np.cos(2 * np.pi * dow / 7.0)
        
        # Rolling Temporal Statistics (short-term & daily trends)
        df_feat['pm25_rolling_mean_3h'] = df_feat['pm25'].rolling(window=3, min_periods=1).mean()
        df_feat['pm25_rolling_mean_24h'] = df_feat['pm25'].rolling(window=24, min_periods=1).mean()
        df_feat['pm10_rolling_mean_3h'] = df_feat['pm10'].rolling(window=3, min_periods=1).mean()
        
        # First difference / rate of change
        df_feat['pm25_diff_1h'] = df_feat['pm25'].diff().fillna(0)
        
        # Domain Interactions
        df_feat['temp_humidity_interaction'] = (df_feat['temperature'] * df_feat['humidity']) / 100.0
        df_feat['ventilation_index'] = df_feat['wind_speed'] * df_feat['temperature']
        df_feat['pm_ratio'] = df_feat['pm25'] / (df_feat['pm10'] + 1e-4)
        
        return df_feat

    def fit_transform(self, df: pd.DataFrame) -> Tuple[np.ndarray, np.ndarray, pd.DataFrame]:
        """
        Executes full preprocessing pipeline and scales features/targets.
        """
        df_processed = self.handle_missing_values(df)
        df_processed = self.handle_outliers(df_processed)
        df_processed = self.engineer_features(df_processed)
        
        # Extract existing features
        available_feats = [col for col in FEATURE_COLUMNS if col in df_processed.columns]
        self.feature_names = available_feats
        
        X_raw = df_processed[available_feats].values
        y_raw = df_processed[[TARGET_COLUMN]].values
        
        X_scaled = self.feature_scaler.fit_transform(X_raw)
        y_scaled = self.target_scaler.fit_transform(y_raw)
        self.is_fitted = True
        
        return X_scaled, y_scaled, df_processed

    def transform(self, df: pd.DataFrame) -> Tuple[np.ndarray, np.ndarray, pd.DataFrame]:
        """Transforms unseen test data using fitted scalers."""
        if not self.is_fitted:
            raise ValueError("Preprocessor must be fitted before calling transform()")
            
        df_processed = self.handle_missing_values(df)
        df_processed = self.handle_outliers(df_processed)
        df_processed = self.engineer_features(df_processed)
        
        X_raw = df_processed[self.feature_names].values
        y_raw = df_processed[[TARGET_COLUMN]].values
        
        X_scaled = self.feature_scaler.transform(X_raw)
        y_scaled = self.target_scaler.transform(y_raw)
        
        return X_scaled, y_scaled, df_processed

    def inverse_transform_target(self, y_scaled: np.ndarray) -> np.ndarray:
        """Denormalizes scaled predictions back to raw AQI unit scale."""
        if not self.is_fitted:
            raise ValueError("Preprocessor must be fitted before inverse transform")
        if y_scaled.ndim == 1:
            y_scaled = y_scaled.reshape(-1, 1)
        return self.target_scaler.inverse_transform(y_scaled)

    def create_sequences(self, X: np.ndarray, y: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """
        Creates sliding window sequences for temporal modeling:
        X_seq shape: (num_samples, sequence_length, num_features)
        y_seq shape: (num_samples, forecast_horizon) or (num_samples,)
        """
        X_seq, y_seq = [], []
        total_len = len(X)
        
        for i in range(total_len - self.sequence_length - self.forecast_horizon + 1):
            x_window = X[i : i + self.sequence_length]
            if self.forecast_horizon == 1:
                y_target = y[i + self.sequence_length, 0]
            else:
                y_target = y[i + self.sequence_length : i + self.sequence_length + self.forecast_horizon, 0]
                
            X_seq.append(x_window)
            y_seq.append(y_target)
            
        return np.array(X_seq, dtype=np.float32), np.array(y_seq, dtype=np.float32)
