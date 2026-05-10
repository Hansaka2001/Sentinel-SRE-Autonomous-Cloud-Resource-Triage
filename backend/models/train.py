"""
train.py
--------
Train an LSTM time-series forecaster for GPU cluster demand.

Pipeline:
  1. Load dataset/processed/hourly_gpu_demand.csv
  2. Use the 'gpu_total' column as the univariate target series
  3. Normalise with MinMaxScaler [0, 1]
  4. Build sliding-window Dataset  (lookback=24h -> forecast 1h ahead)
  5. Define a 2-layer LSTM with a linear output head
  6. Train for 20 epochs with MSELoss + Adam
  7. Save:
       backend/models/gpu_forecaster.pt  -- model weights
       backend/models/scaler.pkl         -- fitted MinMaxScaler

Usage:
    python backend/models/train.py
"""

import os
import pickle
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from torch.utils.data import Dataset, DataLoader
from sklearn.preprocessing import MinMaxScaler

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR   = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_CSV   = os.path.join(BASE_DIR, "dataset", "processed", "hourly_gpu_demand.csv")
MODEL_DIR  = os.path.dirname(os.path.abspath(__file__))
MODEL_PT   = os.path.join(MODEL_DIR, "gpu_forecaster.pt")
SCALER_PKL = os.path.join(MODEL_DIR, "scaler.pkl")

# ---------------------------------------------------------------------------
# Hyper-parameters
# ---------------------------------------------------------------------------
LOOKBACK    = 24    # hours of history fed to the LSTM
FORECAST    = 1     # hours ahead to predict
HIDDEN_DIM  = 64
NUM_LAYERS  = 2
BATCH_SIZE  = 64
EPOCHS      = 20
LR          = 1e-3
TRAIN_SPLIT = 0.85  # 85 % train / 15 % validation

DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")


# ---------------------------------------------------------------------------
# 1. Load and prepare the time-series
# ---------------------------------------------------------------------------
def load_series(path: str) -> np.ndarray:
    """Return the total GPU demand as a 1-D float32 numpy array."""
    df = pd.read_csv(path)

    if "gpu_total" in df.columns:
        series = df["gpu_total"].values.astype(np.float32)
    else:
        # Fallback: sum all gpu_* columns
        gpu_cols = [c for c in df.columns if c.startswith("gpu_")]
        series = df[gpu_cols].sum(axis=1).values.astype(np.float32)

    print(f"[1/5] Loaded series: {len(series):,} hourly points  "
          f"(min={series.min():.2f}, max={series.max():.2f}, mean={series.mean():.2f})")
    return series


# ---------------------------------------------------------------------------
# 2. Normalise
# ---------------------------------------------------------------------------
def fit_scaler(series: np.ndarray):
    scaler = MinMaxScaler(feature_range=(0, 1))
    scaled = scaler.fit_transform(series.reshape(-1, 1)).flatten()
    print("[2/5] Normalised to [0, 1] using MinMaxScaler")
    return scaled, scaler


# ---------------------------------------------------------------------------
# 3. Sliding-window Dataset
# ---------------------------------------------------------------------------
class GPUDemandDataset(Dataset):
    """
    Produces (x, y) pairs where:
      x : float32 tensor of shape (LOOKBACK, 1)  -- past 24 h scaled demand
      y : float32 tensor of shape (1,)            -- next-hour scaled demand
    """

    def __init__(self, scaled: np.ndarray, lookback: int = LOOKBACK):
        self.lookback = lookback
        xs, ys = [], []
        for i in range(len(scaled) - lookback):
            xs.append(scaled[i: i + lookback])
            ys.append(scaled[i + lookback])
        # (N, L, 1)
        self.X = torch.tensor(np.array(xs), dtype=torch.float32).unsqueeze(-1)
        # (N, 1)
        self.Y = torch.tensor(np.array(ys), dtype=torch.float32).unsqueeze(-1)

    def __len__(self):
        return len(self.X)

    def __getitem__(self, idx):
        return self.X[idx], self.Y[idx]


def make_loaders(scaled: np.ndarray):
    dataset = GPUDemandDataset(scaled, lookback=LOOKBACK)
    n_train = int(len(dataset) * TRAIN_SPLIT)
    n_val   = len(dataset) - n_train
    train_ds, val_ds = torch.utils.data.random_split(
        dataset, [n_train, n_val],
        generator=torch.Generator().manual_seed(42),
    )
    train_loader = DataLoader(train_ds, batch_size=BATCH_SIZE, shuffle=True)
    val_loader   = DataLoader(val_ds,   batch_size=BATCH_SIZE, shuffle=False)
    print(f"[3/5] Dataset  -> {len(dataset):,} windows  "
          f"(train={n_train:,}, val={n_val:,})")
    return train_loader, val_loader


# ---------------------------------------------------------------------------
# 4. LSTM Model
# ---------------------------------------------------------------------------
class LSTMForecaster(nn.Module):
    """
    Two-layer LSTM followed by a single linear output layer.

    Input  : (batch, seq_len=LOOKBACK, input_size=1)
    Output : (batch, 1)  -- next-hour scaled demand
    """

    def __init__(
        self,
        input_size:  int   = 1,
        hidden_dim:  int   = HIDDEN_DIM,
        num_layers:  int   = NUM_LAYERS,
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
        # x: (batch, seq_len, 1)
        h0 = torch.zeros(self.num_layers, x.size(0), self.hidden_dim, device=x.device)
        c0 = torch.zeros(self.num_layers, x.size(0), self.hidden_dim, device=x.device)
        out, _ = self.lstm(x, (h0, c0))  # out: (batch, seq_len, hidden_dim)
        last   = out[:, -1, :]           # last time-step
        return self.fc(last)             # (batch, 1)


# ---------------------------------------------------------------------------
# 5. Training loop
# ---------------------------------------------------------------------------
def train_model(model: nn.Module, train_loader: DataLoader, val_loader: DataLoader):
    model.to(DEVICE)
    criterion = nn.MSELoss()
    optimizer = torch.optim.Adam(model.parameters(), lr=LR)

    print(f"[4/5] Training on {DEVICE}  (epochs={EPOCHS}, lr={LR}, batch={BATCH_SIZE})")
    print(f"      Architecture: LSTM(hidden={HIDDEN_DIM}, layers={NUM_LAYERS}) -> Linear(1)")
    print()

    header = f"{'Epoch':>6} | {'Train MSE':>12} | {'Train RMSE':>12} | {'Val MSE':>10} | {'Val RMSE':>10}"
    sep    = "-" * len(header)
    print(header)
    print(sep)

    for epoch in range(1, EPOCHS + 1):
        # -- train --
        model.train()
        train_loss = 0.0
        for xb, yb in train_loader:
            xb, yb = xb.to(DEVICE), yb.to(DEVICE)
            optimizer.zero_grad()
            pred = model(xb)
            loss = criterion(pred, yb)
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
            optimizer.step()
            train_loss += loss.item() * len(xb)
        train_mse = train_loss / len(train_loader.dataset)

        # -- validate --
        model.eval()
        val_loss = 0.0
        with torch.no_grad():
            for xb, yb in val_loader:
                xb, yb = xb.to(DEVICE), yb.to(DEVICE)
                pred = model(xb)
                val_loss += criterion(pred, yb).item() * len(xb)
        val_mse = val_loss / len(val_loader.dataset)

        print(
            f"{epoch:>6} | {train_mse:>12.6f} | {train_mse**0.5:>12.6f} "
            f"| {val_mse:>10.6f} | {val_mse**0.5:>10.6f}"
        )

    return model


# ---------------------------------------------------------------------------
# 6. Save artefacts
# ---------------------------------------------------------------------------
def save_artefacts(model: nn.Module, scaler: MinMaxScaler):
    os.makedirs(MODEL_DIR, exist_ok=True)

    torch.save(model.state_dict(), MODEL_PT)
    print(f"\n[5/5] Model weights saved -> {MODEL_PT}")

    with open(SCALER_PKL, "wb") as f:
        pickle.dump(scaler, f)
    print(f"      Scaler saved         -> {SCALER_PKL}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    print("=" * 62)
    print("  GPU Demand LSTM Forecaster -- Training Pipeline")
    print("=" * 62)
    print(f"  Device   : {DEVICE}")
    print(f"  Lookback : {LOOKBACK} h  |  Forecast horizon: {FORECAST} h")
    print("=" * 62 + "\n")

    series               = load_series(DATA_CSV)
    scaled, scaler       = fit_scaler(series)
    train_loader, val_loader = make_loaders(scaled)

    model = LSTMForecaster()
    model = train_model(model, train_loader, val_loader)
    save_artefacts(model, scaler)

    print("\nDone. Model and scaler are ready for inference via forecaster.py")


if __name__ == "__main__":
    main()
