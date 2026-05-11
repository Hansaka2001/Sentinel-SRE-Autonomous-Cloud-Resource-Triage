"""
main.py
-------
FastAPI Backend for the Sentinel-SRE GPU Triage System.

Endpoints:
  GET  /api/forecast          -- Returns LSTM-predicted GPU demand + cluster capacity
  WS   /ws/triage             -- Runs the LangGraph triage workflow; streams results

Run (from project root):
    python backend/main.py
  or:
    uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
"""

import os
import sys
import json
import asyncio
import logging

import pandas as pd
import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

# ---------------------------------------------------------------------------
# Path bootstrap  (ensures project-root is on sys.path so sub-packages resolve)
# ---------------------------------------------------------------------------
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

# ---------------------------------------------------------------------------
# Load environment variables (.env must contain GEMINI_API_KEY)
# ---------------------------------------------------------------------------
load_dotenv(os.path.join(_PROJECT_ROOT, ".env"), override=True)

# ---------------------------------------------------------------------------
# Internal imports  (after path bootstrap)
# ---------------------------------------------------------------------------
from backend.models.forecaster import predict_next_hour          # noqa: E402
from backend.agents.graph import triage_graph, ClusterState      # noqa: E402

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger("sentinel-sre")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
CLUSTER_CAPACITY = 1000          # GPU units available in the test cluster
_DATA_CSV = os.path.join(_PROJECT_ROOT, "dataset", "processed", "hourly_gpu_demand.csv")
_LOOKBACK = 24                   # hours fed to the LSTM (must match train.py)

# ---------------------------------------------------------------------------
# FastAPI App
# ---------------------------------------------------------------------------
app = FastAPI(
    title="Sentinel-SRE GPU Triage API",
    description=(
        "Autonomous GPU cluster management backend. "
        "Combines LSTM demand forecasting with a LangGraph multi-agent triage workflow "
        "powered by Google Gemini."
    ),
    version="1.0.0",
)

# CORS — allow all origins so the frontend (React / plain HTML) can connect freely
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_recent_24h() -> list[float]:
    """Read the last 24 rows of gpu_total from the processed CSV."""
    df = pd.read_csv(_DATA_CSV, usecols=["gpu_total"])
    recent = df["gpu_total"].tail(_LOOKBACK).tolist()
    if len(recent) < _LOOKBACK:
        raise ValueError(
            f"Not enough data: need {_LOOKBACK} rows, found {len(recent)}."
        )
    return recent


def _build_initial_state(predicted_demand: int) -> ClusterState:
    """Return a fresh ClusterState ready to be fed into the LangGraph."""
    return ClusterState(
        predicted_demand=predicted_demand,
        cluster_capacity=CLUSTER_CAPACITY,
        shortage=0,
        preemption_plan="",
        alert_log="",
    )

# ---------------------------------------------------------------------------
# REST Endpoint: GET /api/forecast
# ---------------------------------------------------------------------------

@app.get("/api/forecast", summary="Get next-hour GPU demand forecast")
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

# ---------------------------------------------------------------------------
# WebSocket Endpoint: ws://localhost:8000/ws/triage
# ---------------------------------------------------------------------------

@app.websocket("/ws/triage")
async def triage_websocket(websocket: WebSocket):
    """
    WebSocket endpoint that drives the full LangGraph triage workflow.

    Client sends:
        { "predicted_demand": <int> }

    Server streams back (one message each as results become available):
        { "event": "shortage",         "data": { "shortage": <int> } }
        { "event": "preemption_plan",  "data": { "preemption_plan": "<str>" } }
        { "event": "alert_log",        "data": { "alert_log": "<str>" } }
        { "event": "done",             "data": {} }

    On no-shortage path:
        { "event": "no_shortage",      "data": { "message": "..." } }
        { "event": "done",             "data": {} }
    """
    await websocket.accept()
    client = websocket.client
    logger.info(f"WS /ws/triage — connection opened from {client}")

    try:
        while True:
            # ---- Receive -------------------------------------------------------
            raw = await websocket.receive_text()
            try:
                payload = json.loads(raw)
                predicted_demand = int(payload["predicted_demand"])
            except (json.JSONDecodeError, KeyError, ValueError) as exc:
                await websocket.send_text(json.dumps({
                    "event": "error",
                    "data": {"message": f"Invalid payload: {exc}"},
                }))
                continue

            logger.info(
                f"WS /ws/triage — received predicted_demand={predicted_demand}"
            )

            initial_state = _build_initial_state(predicted_demand)

            # ---- Stream graph execution in a thread ----------------------------
            # LangGraph's .stream() is synchronous; run it in a thread pool so
            # we don't block the async event loop.
            loop = asyncio.get_event_loop()

            def _run_graph():
                """Execute the graph and collect all node outputs."""
                outputs = {}
                for chunk in triage_graph.stream(
                    initial_state,
                    stream_mode="updates",   # yields per-node state diffs
                ):
                    outputs.update(chunk)
                return outputs

            graph_outputs = await loop.run_in_executor(None, _run_graph)

            # ---- Flatten outputs -----------------------------------------------
            # graph_outputs looks like:
            #   { "analyze_forecast_node": {"shortage": 200, ...},
            #     "scheduler_node":        {"preemption_plan": "...", ...},
            #     "communicator_node":     {"alert_log": "...", ...} }
            # We merge all diffs into one flat dict.
            flat: dict = {}
            for node_update in graph_outputs.values():
                flat.update(node_update)

            shortage = flat.get("shortage", 0)

            # ---- Send results back over the socket ----------------------------
            # Always send shortage first
            await websocket.send_text(json.dumps({
                "event": "shortage",
                "data": {"shortage": shortage},
            }))

            if shortage == 0:
                await websocket.send_text(json.dumps({
                    "event": "no_shortage",
                    "data": {
                        "message": (
                            f"No GPU shortage detected. "
                            f"Predicted demand ({predicted_demand}) is within "
                            f"cluster capacity ({CLUSTER_CAPACITY}). "
                            f"No preemption required."
                        )
                    },
                }))
            else:
                if preemption_plan := flat.get("preemption_plan"):
                    await websocket.send_text(json.dumps({
                        "event": "preemption_plan",
                        "data": {"preemption_plan": preemption_plan},
                    }))

                if alert_log := flat.get("alert_log"):
                    await websocket.send_text(json.dumps({
                        "event": "alert_log",
                        "data": {"alert_log": alert_log},
                    }))

            # Signal completion
            await websocket.send_text(json.dumps({"event": "done", "data": {}}))
            logger.info(f"WS /ws/triage — triage complete (shortage={shortage})")

    except WebSocketDisconnect:
        logger.info(f"WS /ws/triage — client {client} disconnected")
    except Exception as exc:
        logger.exception(f"WS /ws/triage — unhandled error: {exc}")
        try:
            await websocket.send_text(json.dumps({
                "event": "error",
                "data": {"message": str(exc)},
            }))
        except Exception:
            pass  # socket may already be closed

# ---------------------------------------------------------------------------
# Root health-check
# ---------------------------------------------------------------------------

@app.get("/", summary="Health check")
async def root():
    """Simple liveness probe."""
    return {
        "service": "Sentinel-SRE GPU Triage API",
        "status": "running",
        "cluster_capacity": CLUSTER_CAPACITY,
    }

# ---------------------------------------------------------------------------
# Execution block
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    uvicorn.run(
        "backend.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        reload_dirs=[_PROJECT_ROOT],
        log_level="info",
    )
