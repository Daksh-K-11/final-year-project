"""
Air Quality Index (AQI) Calculation Module
Implements standard Central Pollution Control Board (CPCB) and US EPA piecewise linear breakpoint algorithms
for multi-pollutant environmental telemetry.
"""

from typing import Dict, Any, Tuple, Optional
import numpy as np
import pandas as pd

# CPCB Standard Breakpoints: (B_low, B_high, I_low, I_high)
# Concentrations: PM2.5 (ug/m3), PM10 (ug/m3), NO2 (ug/m3), SO2 (ug/m3), CO (mg/m3), O3 (ug/m3)
CPCB_BREAKPOINTS = {
    'PM2.5': [
        (0.0, 30.0, 0, 50),
        (30.1, 60.0, 51, 100),
        (60.1, 90.0, 101, 200),
        (90.1, 120.0, 201, 300),
        (120.1, 250.0, 301, 400),
        (250.1, 500.0, 401, 500)
    ],
    'PM10': [
        (0.0, 50.0, 0, 50),
        (50.1, 100.0, 51, 100),
        (100.1, 250.0, 101, 200),
        (250.1, 350.0, 201, 300),
        (350.1, 430.0, 301, 400),
        (430.1, 600.0, 401, 500)
    ],
    'NO2': [
        (0.0, 40.0, 0, 50),
        (40.1, 80.0, 51, 100),
        (80.1, 180.0, 101, 200),
        (180.1, 280.0, 201, 300),
        (280.1, 400.0, 301, 400),
        (400.1, 600.0, 401, 500)
    ],
    'SO2': [
        (0.0, 40.0, 0, 50),
        (40.1, 80.0, 51, 100),
        (80.1, 380.0, 101, 200),
        (380.1, 800.0, 201, 300),
        (800.1, 1600.0, 301, 400),
        (1600.1, 2000.0, 401, 500)
    ],
    'CO': [  # in mg/m3
        (0.0, 1.0, 0, 50),
        (1.01, 2.0, 51, 100),
        (2.01, 10.0, 101, 200),
        (10.01, 17.0, 201, 300),
        (17.01, 34.0, 301, 400),
        (34.01, 50.0, 401, 500)
    ],
    'O3': [
        (0.0, 50.0, 0, 50),
        (50.1, 100.0, 51, 100),
        (100.1, 168.0, 101, 200),
        (168.1, 208.0, 201, 300),
        (208.1, 748.0, 301, 400),
        (748.1, 1000.0, 401, 500)
    ]
}

AQI_CATEGORIES = [
    (0.0, 50.0, "Good", "#00E400", "Minimal health impact. Air quality is considered satisfactory."),
    (50.0, 100.0, "Satisfactory", "#FFFF00", "Minor breathing discomfort to sensitive people."),
    (100.0, 200.0, "Moderate", "#FF7E00", "Breathing discomfort to people with lungs, asthma and heart diseases."),
    (200.0, 300.0, "Poor", "#FF0000", "Breathing discomfort to most people on prolonged exposure."),
    (300.0, 400.0, "Very Poor", "#8f3f97", "Respiratory illness on prolonged exposure. Significant effects on vulnerable groups."),
    (400.0, 500.0, "Severe", "#7e0023", "Affects healthy people and seriously impacts those with existing diseases.")
]


def calculate_sub_index(pollutant: str, concentration: float) -> Optional[float]:
    """
    Computes pollutant sub-index using linear interpolation formula:
    I_p = ((I_high - I_low) / (B_high - B_low)) * (C_p - B_low) + I_low
    """
    if concentration is None or np.isnan(concentration) or concentration < 0:
        return None
    
    pollutant_key = pollutant.upper().replace('_', '').replace('.', '')
    # Normalize naming
    name_map = {'PM25': 'PM2.5', 'PM10': 'PM10', 'NO2': 'NO2', 'SO2': 'SO2', 'CO': 'CO', 'O3': 'O3'}
    pollutant_std = name_map.get(pollutant_key, pollutant)
    
    if pollutant_std not in CPCB_BREAKPOINTS:
        return None
    
    breakpoints = CPCB_BREAKPOINTS[pollutant_std]
    
    for b_low, b_high, i_low, i_high in breakpoints:
        if b_low <= concentration <= b_high:
            sub_index = ((i_high - i_low) / (b_high - b_low)) * (concentration - b_low) + i_low
            return round(float(sub_index), 2)
            
    # Cap if concentration exceeds highest breakpoint
    max_b = breakpoints[-1]
    if concentration > max_b[1]:
        return float(max_b[3])
        
    return 0.0


def calculate_overall_aqi(pollutants_dict: Dict[str, float]) -> Tuple[float, str, str, str, Dict[str, float]]:
    """
    Computes aggregate AQI as max(sub-indices), determines responsible dominant pollutant,
    AQI category, color code, and health advisory.
    """
    sub_indices = {}
    for pol, val in pollutants_dict.items():
        si = calculate_sub_index(pol, val)
        if si is not None:
            sub_indices[pol] = si
            
    if not sub_indices:
        return 0.0, "Unknown", "#888888", "Insufficient data", {}
        
    overall_aqi = max(sub_indices.values())
    dominant_pollutant = max(sub_indices, key=sub_indices.get)
    
    category = "Severe"
    color = "#7e0023"
    advisory = "Severe pollution. Avoid all outdoor physical activity."
    
    for low, high, cat, col, adv in AQI_CATEGORIES:
        if low <= overall_aqi <= high:
            category = cat
            color = col
            advisory = adv
            break
            
    return round(overall_aqi, 2), dominant_pollutant, category, color, advisory, sub_indices


def categorize_aqi_value(aqi: float) -> Tuple[str, str, str]:
    """Helper to get category, color, and description from raw AQI score."""
    for low, high, cat, col, adv in AQI_CATEGORIES:
        if low <= aqi <= high:
            return cat, col, adv
    if aqi > 500:
        return "Hazardous", "#4B0082", "Hazardous emergency conditions. Serious risk of adverse effects for entire population."
    return "Good", "#00E400", "Air quality is satisfactory."
