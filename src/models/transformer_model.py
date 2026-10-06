"""
Time-Series Transformer with Multi-Head Self-Attention for Air Quality Forecasting
"""

import math
import torch
import torch.nn as nn
import torch.nn.functional as F

class PositionalEncoding(nn.Module):
    """
    Standard sinusoidal positional encoding for time sequences.
    """
    def __init__(self, d_model: int, max_len: int = 500):
        super(PositionalEncoding, self).__init__()
        pe = torch.zeros(max_len, d_model)
        position = torch.arange(0, max_len, dtype=torch.float).unsqueeze(1)
        div_term = torch.exp(torch.arange(0, d_model, 2).float() * (-math.log(10000.0) / d_model))
        pe[:, 0::2] = torch.sin(position * div_term)
        pe[:, 1::2] = torch.cos(position * div_term)
        self.register_buffer('pe', pe.unsqueeze(0))

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # x shape: (batch_size, seq_len, d_model)
        seq_len = x.size(1)
        return x + self.pe[:, :seq_len, :]

class AirQualityTransformer(nn.Module):
    """
    Encoder-based Transformer Architecture tailored for multi-variate environmental time-series.
    """
    def __init__(
        self,
        input_dim: int,
        d_model: int = 64,
        nhead: int = 4,
        num_layers: int = 2,
        dim_feedforward: int = 128,
        output_dim: int = 1,
        dropout: float = 0.1
    ):
        super(AirQualityTransformer, self).__init__()
        self.d_model = d_model
        self.input_embedding = nn.Linear(input_dim, d_model)
        self.pos_encoder = PositionalEncoding(d_model)
        
        encoder_layer = nn.TransformerEncoderLayer(
            d_model=d_model,
            nhead=nhead,
            dim_feedforward=dim_feedforward,
            dropout=dropout,
            batch_first=True,
            activation='gelu'
        )
        self.transformer_encoder = nn.TransformerEncoder(encoder_layer, num_layers=num_layers)
        
        # Dual representation head: immediate sequence recency + global self-attention pooling
        self.head = nn.Sequential(
            nn.Linear(d_model * 2, 48),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(48, output_dim)
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # x: (batch_size, seq_len, input_dim)
        x_emb = self.input_embedding(x) * math.sqrt(self.d_model)
        x_pos = self.pos_encoder(x_emb)
        encoded = self.transformer_encoder(x_pos)  # (batch_size, seq_len, d_model)
        
        # Dual aggregation: recency token at t and global sequence pooling
        pooled = torch.mean(encoded, dim=1)  # (batch_size, d_model)
        last_step = encoded[:, -1, :]  # (batch_size, d_model)
        combined = torch.cat([last_step, pooled], dim=-1)  # (batch_size, d_model * 2)
        
        out = self.head(combined)
        return out.squeeze(-1) if out.shape[-1] == 1 else out

