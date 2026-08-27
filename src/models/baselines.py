"""
Baseline Regression Models (Linear Regression, Random Forest) for AQI benchmarking.
"""

from typing import Dict, Any, Tuple
import numpy as np
from sklearn.linear_model import LinearRegression, Ridge
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

class BaselineModels:
    """
    Implements traditional statistical & ML baselines.
    """
    def __init__(self):
        self.lr_model = LinearRegression()
        self.rf_model = RandomForestRegressor(n_estimators=100, max_depth=12, random_state=42, n_jobs=-1)
        
    def flatten_sequences(self, X_seq: np.ndarray) -> np.ndarray:
        # X_seq: (N, T, D) -> (N, T * D)
        return X_seq.reshape(X_seq.shape[0], -1)

    def fit_and_evaluate(
        self,
        X_train_seq: np.ndarray,
        y_train: np.ndarray,
        X_test_seq: np.ndarray,
        y_test: np.ndarray
    ) -> Dict[str, Dict[str, float]]:
        X_tr_flat = self.flatten_sequences(X_train_seq)
        X_te_flat = self.flatten_sequences(X_test_seq)
        
        # 1. Linear Regression
        self.lr_model.fit(X_tr_flat, y_train)
        lr_preds = self.lr_model.predict(X_te_flat)
        lr_mae = mean_absolute_error(y_test, lr_preds)
        lr_rmse = np.sqrt(mean_squared_error(y_test, lr_preds))
        lr_r2 = r2_score(y_test, lr_preds)
        
        # 2. Random Forest Regressor
        self.rf_model.fit(X_tr_flat, y_train)
        rf_preds = self.rf_model.predict(X_te_flat)
        rf_mae = mean_absolute_error(y_test, rf_preds)
        rf_rmse = np.sqrt(mean_squared_error(y_test, rf_preds))
        rf_r2 = r2_score(y_test, rf_preds)
        
        return {
            'Linear Regression': {
                'MAE': round(float(lr_mae), 3),
                'RMSE': round(float(lr_rmse), 3),
                'R2_Score': round(float(lr_r2), 4),
                'predictions': lr_preds
            },
            'Random Forest': {
                'MAE': round(float(rf_mae), 3),
                'RMSE': round(float(rf_rmse), 3),
                'R2_Score': round(float(rf_r2), 4),
                'predictions': rf_preds
            }
        }
