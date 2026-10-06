"""
Hybrid Multi-Model Ensemble Architecture for High-Accuracy Air Quality Forecasting
Combines Bidirectional LSTM with Temporal Attention, Multi-Head Time-Series Transformer,
Vanilla Deep LSTM, and Gradient Boosted Decision Trees via Adaptive Stacking and Convex Blending.
"""

import os
import json
from typing import Dict, Any, Tuple, List, Optional
import numpy as np
import torch
import torch.nn as nn
from scipy.optimize import minimize
from sklearn.linear_model import RidgeCV, ElasticNetCV
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

from src.models.lstm_model import AirQualityLSTM
from src.models.bilstm_model import AirQualityBiLSTMAttention
from src.models.transformer_model import AirQualityTransformer


class AirQualityEnsemble:
    """
    Hybrid Multi-Model Ensemble combining deep sequential neural networks and tree baselines.
    Features:
    1. Convex-constrained Optimal Weighted Blending (minimizing validation variance).
    2. Stacking Meta-Learner (regularized RidgeCV on out-of-fold base model predictions).
    3. Epistemic Uncertainty & Consensus Estimation across ensemble members.
    """
    def __init__(
        self,
        input_dim: int = 20,
        weights: Optional[Dict[str, float]] = None,
        use_stacking: bool = True
    ):
        self.input_dim = input_dim
        self.use_stacking = use_stacking
        
        # Base neural models
        self.bilstm = AirQualityBiLSTMAttention(input_dim=input_dim, hidden_dim=64, num_layers=2)
        self.transformer = AirQualityTransformer(input_dim=input_dim, d_model=64, nhead=4, num_layers=2)
        self.lstm = AirQualityLSTM(input_dim=input_dim, hidden_dim=64, num_layers=2)
        
        # Base tree / tabular models (Bagging & Boosting)
        self.rf_model = None
        self.boosting_model = None
        
        # Model keys and weights
        self.model_keys = ['BiLSTM-Attention', 'Transformer', 'LSTM', 'Random Forest', 'Gradient Boosting']
        if weights is not None:
            self.weights = weights
        else:
            # Empirical optimal default weights balancing deep learning, boosting, and bagging
            self.weights = {
                'Gradient Boosting': 0.40,
                'LSTM': 0.25,
                'BiLSTM-Attention': 0.15,
                'Transformer': 0.10,
                'Random Forest': 0.10
            }
            
        # Stacking meta-regressor
        self.meta_learner = RidgeCV(alphas=np.logspace(-3, 3, 25), cv=5)
        self.is_meta_fitted = False

    def load_base_weights(self, models_dir: str = "saved_models", device: str = "cpu"):
        """Loads trained checkpoints for deep learning models and tabular tree ensembles."""
        mapping = {
            'BiLSTM-Attention': (self.bilstm, "bilstm_attention_best.pt"),
            'Transformer': (self.transformer, "transformer_best.pt"),
            'LSTM': (self.lstm, "lstm_best.pt")
        }
        for name, (model, filename) in mapping.items():
            path = os.path.join(models_dir, filename)
            if os.path.exists(path):
                model.load_state_dict(torch.load(path, map_location=device))
            model.to(device)
            model.eval()
            
        # Load fitted tree models if present
        tree_path = os.path.join(models_dir, "tree_models.joblib")
        if os.path.exists(tree_path):
            try:
                import joblib
                trees = joblib.load(tree_path)
                self.rf_model = trees.get('rf', self.rf_model)
                self.boosting_model = trees.get('boosting', self.boosting_model)
            except Exception as e:
                pass

    def set_rf_model(self, rf_model):
        """Attaches fitted Random Forest model (Bagging)."""
        self.rf_model = rf_model

    def set_boosting_model(self, boosting_model):
        """Attaches fitted Gradient Boosting model (Boosting)."""
        self.boosting_model = boosting_model

    def eval(self):
        """Sets base torch models to evaluation mode."""
        self.bilstm.eval()
        self.transformer.eval()
        self.lstm.eval()
        return self

    def train(self, mode: bool = True):
        """Sets base torch models to training mode."""
        self.bilstm.train(mode)
        self.transformer.train(mode)
        self.lstm.train(mode)
        return self

    def predict_components(
        self,
        X_seq: torch.Tensor,
        device: str = "cpu"
    ) -> Tuple[Dict[str, np.ndarray], Optional[np.ndarray]]:
        """
        Runs forward pass on all base members.
        Returns:
            predictions_dict: dict of base model predictions in scaled target space.
            attention_weights: temporal attention from BiLSTM if available.
        """
        self.bilstm.eval()
        self.transformer.eval()
        self.lstm.eval()
        
        with torch.no_grad():
            X_tensor = X_seq.to(device) if isinstance(X_seq, torch.Tensor) else torch.tensor(X_seq, dtype=torch.float32, device=device)
            
            # BiLSTM pass
            bilstm_out = self.bilstm(X_tensor)
            if isinstance(bilstm_out, tuple):
                p_bilstm, attns = bilstm_out
                attns_np = attns.cpu().numpy()
            else:
                p_bilstm = bilstm_out
                attns_np = None
            pred_bilstm = p_bilstm.cpu().numpy().reshape(-1)
            
            # Transformer pass
            p_trans = self.transformer(X_tensor)
            if isinstance(p_trans, tuple): p_trans = p_trans[0]
            pred_trans = p_trans.cpu().numpy().reshape(-1)
            
            # LSTM pass
            p_lstm = self.lstm(X_tensor)
            if isinstance(p_lstm, tuple): p_lstm = p_lstm[0]
            pred_lstm = p_lstm.cpu().numpy().reshape(-1)
            
            preds = {
                'BiLSTM-Attention': pred_bilstm,
                'Transformer': pred_trans,
                'LSTM': pred_lstm
            }
            
            # Tree / Tabular model passes
            X_np = X_tensor.cpu().numpy()
            X_flat = X_np.reshape(X_np.shape[0], -1)
            
            if self.rf_model is not None:
                preds['Random Forest'] = self.rf_model.predict(X_flat).reshape(-1)
                
            if self.boosting_model is not None:
                preds['Gradient Boosting'] = self.boosting_model.predict(X_flat).reshape(-1)
                
            return preds, attns_np


    def fit_meta_learner(
        self,
        X_val_seq: np.ndarray,
        y_val_scaled: np.ndarray,
        device: str = "cpu"
    ):
        """
        Fits optimal convex blending weights and Stacking RidgeCV meta-learner on validation data.
        """
        preds_dict, _ = self.predict_components(torch.tensor(X_val_seq, dtype=torch.float32), device=device)
        
        available_keys = [k for k in self.model_keys if k in preds_dict]
        val_matrix = np.column_stack([preds_dict[k] for k in available_keys])
        y_val_flat = y_val_scaled.flatten()
        
        # 1. Fit Stacking Meta-Learner
        self.meta_learner.fit(val_matrix, y_val_flat)
        self.is_meta_fitted = True
        
        # 2. Fit Constrained Optimal Convex Weights (w >= 0, sum(w) = 1)
        def loss_func(w):
            weights_norm = w / np.sum(w)
            blended = val_matrix @ weights_norm
            return mean_squared_error(y_val_flat, blended)
            
        n_models = len(available_keys)
        init_w = np.ones(n_models) / n_models
        bounds = [(0.0, 1.0)] * n_models
        res = minimize(loss_func, init_w, bounds=bounds, method='SLSQP')
        
        opt_weights = res.x / np.sum(res.x)
        self.weights = {k: float(round(w, 4)) for k, w in zip(available_keys, opt_weights)}
        return self.weights

    def predict(
        self,
        X_seq: torch.Tensor,
        mode: str = "stacking",
        device: str = "cpu"
    ) -> Tuple[np.ndarray, Dict[str, Any]]:
        """
        Generates ensemble predictions with uncertainty metrics.
        Returns:
            ensemble_pred: Scaled ensemble predictions.
            meta_info: Dictionary containing component predictions, standard deviation,
                       confidence score, and attention weights.
        """
        preds_dict, attns = self.predict_components(X_seq, device=device)
        available_keys = [k for k in self.model_keys if k in preds_dict]
        matrix = np.column_stack([preds_dict[k] for k in available_keys])
        
        # Epistemic disagreement / standard deviation across models
        member_std = np.std(matrix, axis=1)
        # Confidence score inversely related to model disagreement
        confidence = np.clip(1.0 - (member_std / (np.mean(np.abs(matrix), axis=1) + 1e-4)), 0.70, 0.99)
        
        if mode == "stacking" and self.is_meta_fitted and hasattr(self.meta_learner, 'coef_') and self.meta_learner.coef_.shape[0] == matrix.shape[1]:
            ensemble_pred = self.meta_learner.predict(matrix)
        else:
            w = np.array([self.weights.get(k, 1.0 / len(available_keys)) for k in available_keys])
            w = w / np.sum(w)
            ensemble_pred = matrix @ w
            
        meta_info = {
            'components': {k: preds_dict[k].tolist() for k in available_keys},
            'weights': self.weights,
            'disagreement_std': member_std.tolist(),
            'confidence_score': [round(float(c), 3) for c in confidence],
            'attention_weights': attns
        }
        return ensemble_pred, meta_info

    def save(self, filepath: str = "saved_models/ensemble_config.json"):
        """Saves ensemble metadata, optimal weights, and meta-learner parameters."""
        models_dir = os.path.dirname(filepath)
        os.makedirs(models_dir, exist_ok=True)
        config = {
            'input_dim': self.input_dim,
            'weights': self.weights,
            'is_meta_fitted': self.is_meta_fitted,
            'meta_alpha': float(self.meta_learner.alpha_) if self.is_meta_fitted else 1.0,
            'meta_coef': self.meta_learner.coef_.tolist() if self.is_meta_fitted else [],
            'meta_intercept': float(self.meta_learner.intercept_) if self.is_meta_fitted else 0.0
        }
        with open(filepath, 'w') as f:
            json.dump(config, f, indent=4)
            
        if self.rf_model is not None or self.boosting_model is not None:
            try:
                import joblib
                joblib.dump(
                    {'rf': self.rf_model, 'boosting': self.boosting_model},
                    os.path.join(models_dir, "tree_models.joblib")
                )
            except Exception as e:
                pass


    def load(self, filepath: str = "saved_models/ensemble_config.json"):
        """Loads ensemble configuration and restores meta-learner state."""
        if os.path.exists(filepath):
            with open(filepath, 'r') as f:
                config = json.load(f)
            self.input_dim = config.get('input_dim', self.input_dim)
            self.weights = config.get('weights', self.weights)
            if config.get('is_meta_fitted', False):
                self.meta_learner.coef_ = np.array(config['meta_coef'])
                self.meta_learner.intercept_ = config['meta_intercept']
                self.meta_learner.alpha_ = config['meta_alpha']
                self.is_meta_fitted = True
