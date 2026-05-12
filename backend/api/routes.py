"""
routes.py
---------
REST API endpoints for Sentinel-SRE GPU Triage System.

Endpoints:
  GET  /api/forecast          -- Returns LSTM-predicted GPU demand + cluster capacity
  GET  /                       -- Health check
"""

import os
import sys
import asyncio
import logging

import pandas as pd
from fastapi import APIRouter

from backend.models.forecaster import predict_next_hour


_PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
_DATA_CSV = os.path.join(_PROJECT_ROOT, "dataset",
                         "processed", "hourly_gpu_demand.csv")
_LOOKBACK = 24  # hours fed to the LSTM (must match train.py)

logger = logging.getLogger("sentinel-sre")

router = APIRouter()

# Configuration (passed in or set as module var)
CLUSTER_CAPACITY = 1000


def set_cluster_capacity(capacity: int):
    """Set the global cluster capacity."""
    global CLUSTER_CAPACITY
    CLUSTER_CAPACITY = capacity


def _load_recent_24h() -> list[float]:
    """Read the last 24 rows of gpu_total from the processed CSV."""
    df = pd.read_csv(_DATA_CSV, usecols=["gpu_total"])
    recent = df["gpu_total"].tail(_LOOKBACK).tolist()
    if len(recent) < _LOOKBACK:
        raise ValueError(
            f"Not enough data: need {_LOOKBACK} rows, found {len(recent)}."
        )
    return recent


@router.get("/api/forecast", summary="Get next-hour GPU demand forecast")
async def get_forecast():
    """
    Reads the last 24 hours of cluster data from the processed CSV,
    runs the LSTM forecaster, and returns the predicted demand alongside
    the current cluster capacity.

    Returns:
        JSON: { "predicted_demand": int, "cluster_capacity": int }
    """
    logger.info("GET /api/forecast — loading last 24 h of GPU data")
    recent_24h = await asyncio.get_event_loop().run_in_executor(
        None, _load_recent_24h
    )
    predicted = await asyncio.get_event_loop().run_in_executor(
        None, predict_next_hour, recent_24h
    )
    logger.info(
        f"GET /api/forecast — predicted={predicted}, capacity={CLUSTER_CAPACITY}"
    )
    return {
        "predicted_demand": predicted,
        "cluster_capacity": CLUSTER_CAPACITY,
    }


@router.get("/", summary="Health check")
async def root():
    """Simple liveness probe."""
    return {
        "service": "Sentinel-SRE GPU Triage API",
        "status": "running",
        "cluster_capacity": CLUSTER_CAPACITY,
    }
