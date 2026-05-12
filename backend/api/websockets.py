"""
websockets.py
-------------
WebSocket endpoints for Sentinel-SRE GPU Triage System.

Endpoints:
  WS   /ws/triage             -- Runs the LangGraph triage workflow; streams results
"""

import os
import json
import asyncio
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend.agents.graph import triage_graph, ClusterState


_PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)

logger = logging.getLogger("sentinel-sre")

router = APIRouter()

# Configuration (passed in or set as module var)
CLUSTER_CAPACITY = 1000


def set_cluster_capacity(capacity: int):
    """Set the global cluster capacity."""
    global CLUSTER_CAPACITY
    CLUSTER_CAPACITY = capacity


def _build_initial_state(predicted_demand: int) -> ClusterState:
    """Return a fresh ClusterState ready to be fed into the LangGraph."""
    return ClusterState(
        predicted_demand=predicted_demand,
        cluster_capacity=CLUSTER_CAPACITY,
        shortage=0,
        preemption_plan="",
        alert_log="",
    )


@router.websocket("/ws/triage")
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

            flat: dict = {}
            for node_update in graph_outputs.values():
                flat.update(node_update)

            shortage = flat.get("shortage", 0)

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
            logger.info(
                f"WS /ws/triage — triage complete (shortage={shortage})")

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
            pass 
