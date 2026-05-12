"""
graph.py
--------
LangGraph Multi-Agent Triage Workflow for GPU Cluster Scheduling.

State Machine:
    START
      |
      v
  analyze_forecast_node
      |
      +--- shortage == 0 --> END
      |
      +--- shortage > 0  --> scheduler_node
                                 |
                                 v
                           communicator_node
                                 |
                                 v
                                END

Nodes:
  analyze_forecast_node  -- Pure logic: computes shortage = predicted_demand - cluster_capacity
  scheduler_node         -- Gemini LLM: generates a Kubernetes preemption plan
  communicator_node      -- Gemini LLM: writes a formatted SRE incident alert log

Usage:
    python backend/agents/graph.py
"""

import os
from typing import TypedDict
from dotenv import load_dotenv

from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import StateGraph, END
from langchain_groq import ChatGroq

class ClusterState(TypedDict):
    predicted_demand:  int   # GPU units forecast for next hour
    cluster_capacity:  int   # Current available GPU capacity
    shortage:          int   # Computed gap (demand - capacity), 0 if no shortage
    preemption_plan:   str   # LLM-generated K8s preemption plan
    alert_log:         str   # LLM-generated SRE incident log


def _get_llm():
    """Return a Groq LLM instance for fast, free tier inference."""
    
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise EnvironmentError("GROQ_API_KEY not found in .env file.")
        
    return ChatGroq(
        groq_api_key=api_key, 
        model_name="llama-3.1-8b-instant",
        temperature=0.3
    )



def analyze_forecast_node(state: ClusterState) -> ClusterState:
    """
    Pure-logic node.
    Computes the GPU shortage = predicted_demand - cluster_capacity.
    If demand does not exceed capacity, shortage is set to 0.
    """
    predicted = state["predicted_demand"]
    capacity  = state["cluster_capacity"]
    shortage  = max(0, predicted - capacity)

    print(
        f"[analyze_forecast_node] predicted={predicted} | "
        f"capacity={capacity} | shortage={shortage}"
    )
    return {**state, "shortage": shortage}


def scheduler_node(state: ClusterState) -> ClusterState:
    """
    LLM-powered node.
    Prompts Gemini to act as a Kubernetes cluster scheduler and produce
    a concise, technical preemption plan for the GPU shortage.
    """
    shortage  = state["shortage"]
    predicted = state["predicted_demand"]
    capacity  = state["cluster_capacity"]

    llm = _get_llm()

    prompt = (
        f"You are an autonomous Kubernetes Cluster Scheduler for a GPU cluster.\n"
        f"Current situation:\n"
        f"  - Predicted GPU demand for the next hour: {predicted} units\n"
        f"  - Current cluster capacity: {capacity} units\n"
        f"  - GPU shortage: {shortage} units\n\n"
        f"Generate a concise, technical preemption plan to free up {shortage} GPU units "
        f"by preempting low-priority Spot workloads to accommodate High Priority jobs.\n"
        f"Be specific: mention the number of instances, partition names (e.g., partition-A, "
        f"partition-B), and the action taken (evict / checkpoint / reschedule).\n"
        f"Output ONLY the plan — no preamble, no markdown, no bullet points. "
        f"One or two sentences maximum."
    )

    response = llm.invoke(prompt)
    plan = response.content.strip()

    print(f"[scheduler_node] Preemption plan generated ({len(plan)} chars)")
    return {**state, "preemption_plan": plan}


def communicator_node(state: ClusterState) -> ClusterState:
    """
    LLM-powered node.
    Prompts Gemini to summarise the triage event as a formatted SRE incident log.
    """
    llm = _get_llm()

    prompt = (
        f"You are an SRE incident-management system. Generate a strict, formatted alert log "
        f"for the following GPU cluster triage event.\n\n"
        f"Event details:\n"
        f"  - Predicted GPU demand: {state['predicted_demand']} units\n"
        f"  - Cluster capacity: {state['cluster_capacity']} units\n"
        f"  - GPU shortage detected: {state['shortage']} units\n"
        f"  - Preemption plan executed: {state['preemption_plan']}\n\n"
        f"Format the log EXACTLY as follows (fill in the values):\n"
        f"[ALERT] SEVERITY=HIGH  SOURCE=Sentinel-SRE\n"
        f"TIMESTAMP=<ISO-8601 timestamp>\n"
        f"EVENT=GPU_SHORTAGE_DETECTED\n"
        f"PREDICTED_DEMAND=<value>\n"
        f"CLUSTER_CAPACITY=<value>\n"
        f"SHORTAGE=<value>\n"
        f"ACTION_TAKEN=<one-sentence summary of the preemption plan>\n"
        f"STATUS=RESOLVED\n"
        f"Output ONLY the formatted log block. No extra text."
    )

    response = llm.invoke(prompt)
    alert_log = response.content.strip()

    print(f"[communicator_node] Alert log generated ({len(alert_log)} chars)")
    return {**state, "alert_log": alert_log}



def _route_after_analysis(state: ClusterState) -> str:
    """Route to scheduler if there is a GPU shortage, otherwise end."""
    return "scheduler_node" if state["shortage"] > 0 else END


def build_graph() -> StateGraph:
    """Assemble and compile the LangGraph state machine."""
    graph = StateGraph(ClusterState)

    # Register nodes
    graph.add_node("analyze_forecast_node", analyze_forecast_node)
    graph.add_node("scheduler_node",        scheduler_node)
    graph.add_node("communicator_node",     communicator_node)

    # Entry point
    graph.set_entry_point("analyze_forecast_node")

    # Conditional edge after analysis
    graph.add_conditional_edges(
        "analyze_forecast_node",
        _route_after_analysis,
        {
            "scheduler_node": "scheduler_node",
            END:              END,
        },
    )

    # Linear edges for the shortage path
    graph.add_edge("scheduler_node",    "communicator_node")
    graph.add_edge("communicator_node", END)

    return graph.compile()


# Compiled graph (module-level singleton for import by other modules)
triage_graph = build_graph()


if __name__ == "__main__":
    load_dotenv()

    print("=" * 60)
    print("  Sentinel-SRE  |  LangGraph Triage Workflow -- Self-Test")
    print("=" * 60)

    # Dummy state: 200-GPU shortage
    initial_state: ClusterState = {
        "predicted_demand":  1200,
        "cluster_capacity":  1000,
        "shortage":          0,
        "preemption_plan":   "",
        "alert_log":         "",
    }

    print(f"\nRunning graph with: predicted_demand=1200, cluster_capacity=1000\n")

    final_state = triage_graph.invoke(initial_state)

    print("\n" + "=" * 60)
    print("  FINAL ALERT LOG")
    print("=" * 60)
    print(final_state["alert_log"])
    print("=" * 60)
    print("\n[PASS] LangGraph workflow completed successfully.")
