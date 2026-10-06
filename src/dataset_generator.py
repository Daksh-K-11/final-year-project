"""
Campus IoT Environmental Sensor Dataset Generator
Generates realistic multi-station hourly time-series data with diurnal, weekly,
seasonal dynamics, photochemical reactions, traffic spikes, weather interactions,
and typical IoT sensor artifacts (noise, drift, packet loss).
"""

import os
import math
from typing import Tuple, List, Dict, Optional
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from src.aqi_calculator import calculate_overall_aqi, calculate_sub_index

def generate_campus_iot_dataset(
    start_date: str = "2025-01-01 00:00:00",
    num_days: int = 365,
    station_id: str = "CAMPUS_MAIN_STATION",
    missing_rate: float = 0.03,
    noise_level: float = 0.05,
    random_seed: int = 42
) -> pd.DataFrame:
    """
    Synthesizes physical time-series environmental data representing a university campus station.
    """
    np.random.seed(random_seed)
    
    start_dt = datetime.strptime(start_date, "%Y-%m-%d %H:%M:%S")
    total_hours = num_days * 24
    timestamps = [start_dt + timedelta(hours=i) for i in range(total_hours)]
    
    df = pd.DataFrame({'timestamp': timestamps})
    df['hour'] = df['timestamp'].dt.hour
    df['day_of_week'] = df['timestamp'].dt.dayofweek
    df['month'] = df['timestamp'].dt.month
    df['day_of_year'] = df['timestamp'].dt.dayofyear
    df['is_weekend'] = df['day_of_week'].isin([5, 6]).astype(int)
    
    # 1. Weather Dynamics
    # Temperature: Winter low (~12C), Summer high (~38C), Diurnal swing (peaks ~14:00, trough ~05:00)
    seasonal_temp = 25 - 10 * np.cos(2 * np.pi * (df['day_of_year'] - 15) / 365)
    diurnal_temp = 5 * np.sin(2 * np.pi * (df['hour'] - 9) / 24)
    temp_noise = np.random.normal(0, 1.2, total_hours)
    df['temperature'] = np.clip(seasonal_temp + diurnal_temp + temp_noise, 8.0, 46.0)
    
    # Humidity: Inversely correlated with temperature + monsoon peak (July-Sept: months 7,8,9)
    monsoon_boost = 25 * np.exp(-0.5 * ((df['month'] - 8) / 1.2) ** 2)
    diurnal_humidity = -15 * np.sin(2 * np.pi * (df['hour'] - 9) / 24)
    base_humidity = 55 + monsoon_boost + diurnal_humidity + np.random.normal(0, 3.0, total_hours)
    df['humidity'] = np.clip(base_humidity, 15.0, 98.0)
    
    # Wind Speed: Higher in afternoon, calmer at night/winter
    df['wind_speed'] = np.clip(2.5 + 1.8 * np.sin(2 * np.pi * (df['hour'] - 11) / 24) + np.random.exponential(1.0, total_hours), 0.2, 14.0)
    
    # 2. Activity & Campus Traffic Index (0.0 to 1.0)
    # Rush hours: 8:00 - 10:00 and 17:00 - 19:30 on weekdays; lower on weekends
    morning_rush = np.exp(-0.5 * ((df['hour'] - 9) / 1.5) ** 2)
    evening_rush = np.exp(-0.5 * ((df['hour'] - 18) / 1.8) ** 2)
    base_traffic = (0.2 + 0.5 * morning_rush + 0.45 * evening_rush) * (1 - 0.45 * df['is_weekend'])
    traffic_noise = np.random.uniform(-0.05, 0.08, total_hours)
    df['campus_activity_index'] = np.clip(base_traffic + traffic_noise, 0.05, 1.0)
    
    # 3. Pollutant Concentrations Generation
    # Winter inversion multiplier (Oct-Feb: months 10,11,12,1,2)
    is_winter = df['month'].isin([11, 12, 1, 2]).astype(float)
    inversion_factor = 1.0 + 0.75 * is_winter - 0.25 * (df['wind_speed'] / 5.0)
    
    # PM2.5 (Fine Particulate Matter) with atmospheric persistence (advection-diffusion continuity)
    base_pm25 = (28.0 + 45.0 * df['campus_activity_index']) * inversion_factor
    pm25_rain_washout = (df['humidity'] > 85).astype(float) * 0.45
    pm25_target = base_pm25 * (1.0 - pm25_rain_washout)
    
    pm25_series = np.zeros(total_hours)
    pm25_series[0] = pm25_target.iloc[0]
    for t in range(1, total_hours):
        # Physical fluid persistence (alpha=0.78) driven by emission source + calibrated sensor jitter
        pm25_series[t] = 0.78 * pm25_series[t-1] + 0.22 * pm25_target.iloc[t] + np.random.normal(0, 1.2)
    df['pm25'] = np.clip(pm25_series, 5.0, 480.0)
    
    # PM10 (Coarse Particulate Matter with smooth meteorological dynamics)
    dust_factor = (df['wind_speed'] > 5.0).astype(float) * 12.0
    pm10_series = np.zeros(total_hours)
    pm10_series[0] = df['pm25'].iloc[0] * 1.75
    for t in range(1, total_hours):
        ratio = 1.75 + 0.12 * np.sin(2 * np.pi * df['hour'].iloc[t] / 24)
        target_pm10 = df['pm25'].iloc[t] * ratio + dust_factor.iloc[t]
        pm10_series[t] = 0.78 * pm10_series[t-1] + 0.22 * target_pm10 + np.random.normal(0, 2.0)
    df['pm10'] = np.clip(pm10_series, 10.0, 650.0)
    
    # NO2 (Nitrogen Dioxide: strictly tied to vehicular emission & transit)
    df['no2'] = np.clip((15.0 + 38.0 * df['campus_activity_index'] * inversion_factor) + np.random.normal(0, 1.5, total_hours), 4.0, 220.0)
    
    # SO2 (Sulfur Dioxide: background industrial drift)
    df['so2'] = np.clip(8.0 + 6.5 * inversion_factor + np.random.normal(0, 0.8, total_hours), 2.0, 95.0)
    
    # CO (Carbon Monoxide in mg/m3)
    df['co'] = np.clip((0.4 + 1.5 * df['campus_activity_index'] * inversion_factor) + np.random.normal(0, 0.05, total_hours), 0.1, 8.5)
    
    # O3 (Ozone: photochemical byproduct, peaks with high sunlight/temperature and NO2)
    sunlight_intensity = np.clip(np.sin(np.pi * (df['hour'] - 6) / 12), 0, 1) * (df['temperature'] / 30.0)
    df['o3'] = np.clip(10.0 + 62.0 * sunlight_intensity + np.random.normal(0, 1.5, total_hours), 2.0, 180.0)
    
    # 4. Station Metadata
    df['station_id'] = station_id
    
    # 5. Compute Ground Truth AQI and Sub-indices
    aqi_list = []
    category_list = []
    dom_pollutant_list = []
    
    for idx, row in df.iterrows():
        pols = {
            'PM2.5': row['pm25'],
            'PM10': row['pm10'],
            'NO2': row['no2'],
            'SO2': row['so2'],
            'CO': row['co'],
            'O3': row['o3']
        }
        res = calculate_overall_aqi(pols)
        aqi_list.append(res[0])
        dom_pollutant_list.append(res[1])
        category_list.append(res[2])
        
    df['aqi'] = aqi_list
    df['dominant_pollutant'] = dom_pollutant_list
    df['aqi_category'] = category_list
    
    # 6. Simulate Real-world IoT missing data / packet dropouts
    if missing_rate > 0:
        telemetry_cols = ['pm25', 'pm10', 'no2', 'so2', 'co', 'o3', 'temperature', 'humidity', 'wind_speed']
        for col in telemetry_cols:
            mask = np.random.rand(len(df)) < missing_rate
            df.loc[mask, col] = np.nan
            
    # Round numerical fields
    for col in ['pm25', 'pm10', 'no2', 'so2', 'co', 'o3', 'temperature', 'humidity', 'wind_speed', 'aqi']:
        if col in df.columns:
            df[col] = df[col].round(2)
            
    return df

def save_default_datasets(output_dir: str = "data") -> Tuple[str, str]:
    """Generates and persists raw and preprocessed datasets for academic review."""
    os.makedirs(output_dir, exist_ok=True)
    raw_path = os.path.join(output_dir, "campus_air_quality_raw.csv")
    
    print("[Dataset Generator] Generating 1-Year Campus IoT Sensor Telemetry (8760 hourly records)...")
    df_raw = generate_campus_iot_dataset(
        start_date="2025-01-01 00:00:00",
        num_days=365,
        missing_rate=0.02,  # 2% realistic IoT transmission packet loss
        noise_level=0.02
    )
    df_raw.to_csv(raw_path, index=False)
    print(f"[Dataset Generator] Successfully saved raw dataset to: {raw_path}")
    print(f"Dataset shape: {df_raw.shape}")
    print(df_raw[['timestamp', 'pm25', 'pm10', 'no2', 'co', 'o3', 'temperature', 'humidity', 'aqi', 'aqi_category']].head())
    
    return raw_path

if __name__ == "__main__":
    save_default_datasets()
