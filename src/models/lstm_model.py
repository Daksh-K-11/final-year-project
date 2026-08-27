"""
Long Short-Term Memory (LSTM) Architecture for Air Quality Forecasting
"""

import torch
import torch.nn as nn

class AirQualityLSTM(nn.Module):
    """
    Standard multi-layer LSTM network for multivariate time-series AQI prediction.
    """
    def __init__(
        self,
        input_dim: int,
        hidden_dim: int = 64,
        num_layers: int = 2,
        output_dim: int = 1,
        dropout: float = 0.2
    ):
        super(AirQualityLSTM, self).__init__()
        self.hidden_dim = hidden_dim
        self.num_layers = num_layers
        
        self.lstm = nn.LSTM(
            input_size=input_dim,
            hidden_size=hidden_dim,
            num_layers=num_layers,
            batch_first=True,
            dropout=dropout if num_layers > 1 else 0.0
        )
        
        self.dropout = nn.Dropout(dropout)
        self.fc1 = nn.Linear(hidden_dim, 32)
        self.relu = nn.ReLU()
        self.fc2 = nn.Linear(32, output_dim)
        
    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # x shape: (batch_size, seq_len, input_dim)
        lstm_out, (h_n, c_n) = self.lstm(x)
        # Take the last hidden state representing the sequence
        last_hidden = lstm_out[:, -1, :]
        
        out = self.dropout(last_hidden)
        out = self.fc1(out)
        out = self.relu(out)
        out = self.fc2(out)
        
        return out.squeeze(-1) if out.shape[-1] == 1 else out
