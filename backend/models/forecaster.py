"""
forecaster.py
-------------
Inference wrapper for the trained LSTM GPU-demand forecaster.

Public API:
    predict_next_hour(recent_24h_data) -> int

    Args:
        recent_24h_data : array-like of length 24 containing the raw (unscaled)
                          gpu_total demand values for the last 24 consecutive hours.

    Returns:
        Predicted total GPU demand for the next hour as an integer.

The function lazy-loads the model and scaler on first call and caches them in
module-level globals so repeated calls don't reload from disk.
"""

import os
import pickle
import numpy as np
import torch
import torch.nn as nn

# ---------------------------------------------------------------------------
# Paths (resolved relative to this file's location)
# ---------------------------------------------------------------------------
_MODEL_DIR  = os.path.dirname(os.path.abspath(__file__))
_MODEL_PT   = os.path.join(_MODEL_DIR, "gpu_forecaster.pt")
_SCALER_PKL = os.path.join(_MODEL_DIR, "scaler.pkl")

# ---------------------------------------------------------------------------
# LSTM architecture  (must match train.py exactly)
# ---------------------------------------------------------------------------
_HIDDEN_DIM = 64
_NUM_LAYERS = 2
_LOOKBACK   = 24

_DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")


class _LSTMForecaster(nn.Module):
    """Mirror of the LSTMForecaster defined in train.py."""

    def __init__(
        self,
        input_size:  int   = 1,
        hidden_dim:  int   = _HIDDEN_DIM,
        num_layers:  int   = _NUM_LAYERS,
        output_size: int   = 1,
        dropout:     float = 0.2,
    ):
        super().__init__()
        self.hidden_dim = hidden_dim
        self.num_layers = num_layers

        self.lstm = nn.LSTM(
            input_size  = input_size,
            hidden_size = hidden_dim,
            num_layers  = num_layers,
            batch_first = True,
            dropout     = dropout if num_layers > 1 else 0.0,
        )
        self.fc = nn.Linear(hidden_dim, output_size)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        h0 = torch.zeros(self.num_layers, x.size(0), self.hidden_dim, device=x.device)
        c0 = torch.zeros(self.num_layers, x.size(0), self.hidden_dim, device=x.device)
        out, _ = self.lstm(x, (h0, c0))
        return self.fc(out[:, -1, :])


# ---------------------------------------------------------------------------
# Module-level cache (lazy-loaded on first inference call)
# ---------------------------------------------------------------------------
_model  = None
_scaler = None


def _load_artefacts():
    """Load model and scaler from disk (called once)."""
    global _model, _scaler

    if not os.path.exists(_MODEL_PT):
        raise FileNotFoundError(
            f"Model weights not found at {_MODEL_PT}. "
            "Run `python backend/models/train.py` first."
        )
    if not os.path.exists(_SCALER_PKL):
        raise FileNotFoundError(
            f"Scaler not found at {_SCALER_PKL}. "
            "Run `python backend/models/train.py` first."
        )

    # Load scaler
    with open(_SCALER_PKL, "rb") as f:
        _scaler = pickle.load(f)

    # Load model
    _model = _LSTMForecaster()
    _model.load_state_dict(torch.load(_MODEL_PT, map_location=_DEVICE))
    _model.to(_DEVICE)
    _model.eval()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def predict_next_hour(recent_24h_data) -> int:
    """
    Predict total GPU demand for the next hour.

    Parameters
    ----------
    recent_24h_data : array-like, length == 24
        Raw (unscaled) gpu_total values for the most-recent 24 consecutive hours.

    Returns
    -------
    int
        Predicted GPU demand for the next hour (rounded to nearest integer).

    Raises
    ------
    ValueError
        If the input does not contain exactly 24 data points.
    FileNotFoundError
        If model weights or scaler have not been generated yet.
    """
    data = np.asarray(recent_24h_data, dtype=np.float32)
    if data.shape[0] != _LOOKBACK:
        raise ValueError(
            f"Expected exactly {_LOOKBACK} hourly data points, got {data.shape[0]}."
        )

    # Lazy-load on first call
    if _model is None or _scaler is None:
        _load_artefacts()

    # Scale input
    scaled_input = _scaler.transform(data.reshape(-1, 1)).flatten()

    # Build tensor: (1, 24, 1)
    x = torch.tensor(scaled_input, dtype=torch.float32).unsqueeze(0).unsqueeze(-1)
    x = x.to(_DEVICE)

    # Run inference
    with torch.no_grad():
        scaled_pred = _model(x).item()          # scalar in [0, 1]

    # Inverse-transform to original scale
    raw_pred = _scaler.inverse_transform([[scaled_pred]])[0][0]

    return int(round(float(raw_pred)))


# ---------------------------------------------------------------------------
# Quick self-test when run directly
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import pandas as pd

    print("Running self-test for forecaster.py ...")

    _BASE_DIR = os.path.dirname(os.path.dirname(_MODEL_DIR))
    _DATA_CSV = os.path.join(_BASE_DIR, "dataset", "processed", "hourly_gpu_demand.csv")

    df = pd.read_csv(_DATA_CSV)
    col = "gpu_total" if "gpu_total" in df.columns else df.columns[1]
    sample_24h = df[col].values[:24].tolist()

    print(f"  Input (last 24 h gpu_total): {[round(v, 1) for v in sample_24h]}")
    prediction = predict_next_hour(sample_24h)
    print(f"  Predicted next-hour GPU demand: {prediction}")
