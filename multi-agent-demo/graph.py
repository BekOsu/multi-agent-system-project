"""LangGraph graph definition with Orchestrator-controlled routing."""

import time

from langgraph.graph import StateGraph, END

from state import AgentState
from agents.orchestrator import run_orchestrator
from agents.planner import run_planner
from agents.fe_executor import run_fe_executor
from agents.be_executor import run_be_executor
from agents.validator import run_validator
from observability.metrics import AGENT_LATENCY, AGENT_TOKEN_USAGE
from security.guardrails import (
    register_prompt,
    sanitize_input,
    verify_prompt_integrity,
)
from prompts.orchestrator_prompt import ORCHESTRATOR_SYSTEM
from prompts.planner_prompt import PLANNER_SYSTEM
from prompts.fe_prompt import FE_SYSTEM
from prompts.be_prompt import BE_SYSTEM
from prompts.validator_prompt import VALIDATOR_SYSTEM


# Register all system prompts at import time for integrity verification
register_prompt("orchestrator", ORCHESTRATOR_SYSTEM)
register_prompt("planner", PLANNER_SYSTEM)
register_prompt("fe_executor", FE_SYSTEM)
register_prompt("be_executor", BE_SYSTEM)
register_prompt("validator", VALIDATOR_SYSTEM)


def _guarded(agent_name: str, fn):
    """Wrap an agent function with latency tracking and guardrail middleware."""
    def wrapper(state: AgentState) -> AgentState:
        # Verify prompt integrity before each call
        prompt_map = {
            "orchestrator": ORCHESTRATOR_SYSTEM,
            "planner": PLANNER_SYSTEM,
            "fe_executor": FE_SYSTEM,
            "be_executor": BE_SYSTEM,
            "validator": VALIDATOR_SYSTEM,
        }
        prompt = prompt_map.get(agent_name)
        if prompt and not verify_prompt_integrity(agent_name, prompt):
            return {
                **state,
                "error": f"Prompt integrity check failed for {agent_name}",
                "current_agent": "done",
                "done": True,
            }

        # Sanitize user input on first pass through orchestrator
        if agent_name == "orchestrator" and not state.get("_input_sanitized"):
            sanitized = sanitize_input(state.get("user_request", ""))
            state = {**state, "user_request": sanitized, "_input_sanitized": True}

        start = time.time()
        result = fn(state)
        elapsed = time.time() - start

        AGENT_LATENCY.labels(agent=agent_name).observe(elapsed)

        # Track per-agent token usage in Prometheus
        agent_tokens = result.get("agent_tokens", {})
        if agent_name in agent_tokens:
            AGENT_TOKEN_USAGE.labels(agent=agent_name).inc(
                agent_tokens[agent_name] - state.get("agent_tokens", {}).get(agent_name, 0)
            )

        return result
    return wrapper


def _route_after_orchestrator(state: AgentState) -> str:
    """Route to the agent chosen by the Orchestrator."""
    agent = state.get("current_agent", "done")
    if agent in ("planner", "fe_executor", "be_executor", "validator"):
        return agent
    return "done"


def build_graph() -> StateGraph:
    graph = StateGraph(AgentState)

    # Add nodes wrapped with guardrail middleware
    graph.add_node("orchestrator", _guarded("orchestrator", run_orchestrator))
    graph.add_node("planner", _guarded("planner", run_planner))
    graph.add_node("fe_executor", _guarded("fe_executor", run_fe_executor))
    graph.add_node("be_executor", _guarded("be_executor", run_be_executor))
    graph.add_node("validator", _guarded("validator", run_validator))

    # Entry point
    graph.set_entry_point("orchestrator")

    # Orchestrator decides where to go
    graph.add_conditional_edges(
        "orchestrator",
        _route_after_orchestrator,
        {
            "planner": "planner",
            "fe_executor": "fe_executor",
            "be_executor": "be_executor",
            "validator": "validator",
            "done": END,
        },
    )

    # Every agent returns to Orchestrator for the next decision
    for agent in ("planner", "fe_executor", "be_executor", "validator"):
        graph.add_edge(agent, "orchestrator")

    return graph.compile()
