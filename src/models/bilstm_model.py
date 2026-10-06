"""
Bidirectional LSTM with Temporal Attention Mechanism for AQI Forecasting
"""

import torch
import torch.nn as nn
import torch.nn.functional as F

class TemporalAttention(nn.Module):
    """
    Computes dynamic attention weights over all time steps of the recurrent sequence.
    """
    def __init__(self, hidden_dim: int):
        super(TemporalAttention, self).__init__()
        self.projection = nn.Sequential(
            nn.Linear(hidden_dim, 64),
            nn.Tanh(),
            nn.Linear(64, 1, bias=False)
        )
        
    def forward(self, encoder_outputs: torch.Tensor):
        # encoder_outputs: (batch_size, seq_len, hidden_dim)
        energy = self.projection(encoder_outputs)  # (batch_size, seq_len, 1)
        weights = F.softmax(energy, dim=1)  # (batch_size, seq_len, 1)
        context = torch.sum(encoder_outputs * weights, dim=1)  # (batch_size, hidden_dim)
        return context, weights

class AirQualityBiLSTMAttention(nn.Module):
    """
    Bidirectional LSTM with Temporal Attention and Residual Highway Layer.
    """
    def __init__(
        self,
        input_dim: int,
        hidden_dim: int = 64,
        num_layers: int = 2,
        output_dim: int = 1,
        dropout: float = 0.2
    ):
        super(AirQualityBiLSTMAttention, self).__init__()
        self.hidden_dim = hidden_dim
        self.num_layers = num_layers
        
        self.bilstm = nn.LSTM(
            input_size=input_dim,
            hidden_size=hidden_dim,
            num_layers=num_layers,
            batch_first=True,
            bidirectional=True,
            dropout=dropout if num_layers > 1 else 0.0
        )
        
        # BiLSTM produces 2 * hidden_dim
        self.attention = TemporalAttention(hidden_dim * 2)
        self.dropout = nn.Dropout(dropout)
        
        # Combine immediate sequence recency with global attention context
        self.fc1 = nn.Linear(hidden_dim * 4, 64)
        self.layer_norm = nn.LayerNorm(64)
        self.fc2 = nn.Linear(64, output_dim)
        
    def forward(self, x: torch.Tensor):
        # x: (batch_size, seq_len, input_dim)
        lstm_out, _ = self.bilstm(x)  # (batch_size, seq_len, hidden_dim * 2)
        context, attn_weights = self.attention(lstm_out)  # (batch_size, hidden_dim * 2)
        last_step = lstm_out[:, -1, :]  # (batch_size, hidden_dim * 2)
        combined = torch.cat([last_step, context], dim=-1)  # (batch_size, hidden_dim * 4)
        
        out = self.dropout(combined)
        out = F.gelu(self.layer_norm(self.fc1(out)))
        out = self.fc2(out)
        
        # Return prediction and attention weights for interpretability
        return (out.squeeze(-1) if out.shape[-1] == 1 else out), attn_weights

