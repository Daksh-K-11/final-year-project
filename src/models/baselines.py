"""
Baseline Regression Models (Random Forest, HistGBDT, XGBoost, LightGBM)
for air quality and AQI benchmarking across Bagging and Boosting paradigms.
"""

from typing import Dict, Any, Tuple, Optional
import numpy as np
from sklearn.ensemble import RandomForestRegressor, HistGradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

try:
    import xgboost as xgb
    HAS_XGB = True
except ImportError:
    HAS_XGB = False

try:
    import lightgbm as lgb
    HAS_LGB = True
except ImportError:
    HAS_LGB = False


class BaselineModels:
    """
    Implements traditional ML baselines across:
    1. Bagging ensemble (RandomForestRegressor)
    2. Gradient Boosting decision trees (HistGradientBoosting, XGBoost, LightGBM)
    """
    def __init__(self):
        self.rf_model = RandomForestRegressor(
            n_estimators=100, max_depth=12, max_features='sqrt', random_state=42
        )
        self.hgb_model = HistGradientBoostingRegressor(
            max_iter=150, max_leaf_nodes=31, learning_rate=0.08, random_state=42
        )
        self.xgb_model = (
            xgb.XGBRegressor(
                n_estimators=150, max_depth=5, learning_rate=0.07, tree_method='hist', random_state=42
            ) if HAS_XGB else None
        )
        self.lgb_model = (
            lgb.LGBMRegressor(
                n_estimators=150, max_depth=6, learning_rate=0.07, random_state=42, verbose=-1
            ) if HAS_LGB else None
        )
        
    def flatten_sequences(self, X_seq: np.ndarray) -> np.ndarray:
        # X_seq: (N, T, D) -> (N, T * D)
        return X_seq.reshape(X_seq.shape[0], -1)

    def fit_and_evaluate(
        self,
        X_train_seq: np.ndarray,
        y_train: np.ndarray,
        X_test_seq: np.ndarray,
        y_test: np.ndarray
    ) -> Dict[str, Dict[str, Any]]:
        X_tr_flat = self.flatten_sequences(X_train_seq)
        X_te_flat = self.flatten_sequences(X_test_seq)
        results = {}
        
        # 1. Random Forest Regressor (Bagging)
        self.rf_model.fit(X_tr_flat, y_train)
        rf_preds = self.rf_model.predict(X_te_flat)
        results['Random Forest'] = {
            'MAE': round(float(mean_absolute_error(y_test, rf_preds)), 3),
            'RMSE': round(float(np.sqrt(mean_squared_error(y_test, rf_preds))), 3),
            'R2_Score': round(float(r2_score(y_test, rf_preds)), 4),
            'predictions': rf_preds
        }
        
        # 3. HistGradientBoosting (Boosting)
        self.hgb_model.fit(X_tr_flat, y_train)
        hgb_preds = self.hgb_model.predict(X_te_flat)
        results['HistGBDT (Boosting)'] = {
            'MAE': round(float(mean_absolute_error(y_test, hgb_preds)), 3),
            'RMSE': round(float(np.sqrt(mean_squared_error(y_test, hgb_preds))), 3),
            'R2_Score': round(float(r2_score(y_test, hgb_preds)), 4),
            'predictions': hgb_preds
        }
        
        # 4. XGBoost (Boosting)
        if self.xgb_model is not None:
            self.xgb_model.fit(X_tr_flat, y_train)
            xgb_preds = self.xgb_model.predict(X_te_flat)
            results['XGBoost (Boosting)'] = {
                'MAE': round(float(mean_absolute_error(y_test, xgb_preds)), 3),
                'RMSE': round(float(np.sqrt(mean_squared_error(y_test, xgb_preds))), 3),
                'R2_Score': round(float(r2_score(y_test, xgb_preds)), 4),
                'predictions': xgb_preds
            }
            
        return results

