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
import logging

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware


_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


load_dotenv(os.path.join(_PROJECT_ROOT, ".env"), override=True)


from backend.api import routes, websockets  # noqa: E402


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger("sentinel-sre")


# GPU cluster configuration
CLUSTER_CAPACITY = 1000  # GPU units available in the test cluster

app = FastAPI(
    title="Sentinel-SRE GPU Triage API",
    description=(
        "Autonomous GPU cluster management backend. "
        "Combines LSTM demand forecasting with a LangGraph multi-agent triage workflow "
        "powered by Google Gemini."
    ),
    version="1.0.0",
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Set cluster capacity in API modules
routes.set_cluster_capacity(CLUSTER_CAPACITY)
websockets.set_cluster_capacity(CLUSTER_CAPACITY)

# Include API routers
app.include_router(routes.router)
app.include_router(websockets.router)


if __name__ == "__main__":
    uvicorn.run(
        "backend.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        reload_dirs=[_PROJECT_ROOT],
        log_level="info",
    )
