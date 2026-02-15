"""Entry point for the multi-agent code generator."""

import argparse
import sys
import time
import uuid

from dotenv import load_dotenv

load_dotenv()

from graph import build_graph
from state import AgentState
from tools.file_writer import write_artifacts
from observability.metrics import (
    start_metrics_server,
    TOKENS_USED,
    COST_PER_PROJECT,
    JOB_DURATION,
)
from scaling.config import JOB_TOKEN_BUDGET

DEFAULT_REQUEST = "Build a todo app with user authentication, task CRUD, and a dashboard"


def _print_cost_summary(state: dict) -> None:
    """Print per-agent token usage table, cost breakdown, and retry info."""
    print("\n  Per-Agent Token Usage:")
    print(f"  {'Agent':<16} {'Tokens':>10} {'Cost (USD)':>12}")
    print(f"  {'-'*40}")
    agent_tokens = state.get("agent_tokens", {})
    cost_breakdown = state.get("cost_breakdown", {})
    for agent in ("orchestrator", "planner", "fe_executor", "be_executor", "validator"):
        tokens = agent_tokens.get(agent, 0)
        cost = cost_breakdown.get(agent, 0.0)
        if tokens > 0:
            print(f"  {agent:<16} {tokens:>10,} ${cost:>11.6f}")
    print(f"  {'-'*40}")
    print(f"  {'TOTAL':<16} {state.get('total_tokens', 0):>10,} ${state.get('cost_usd', 0.0):>11.6f}")

    # Security warnings
    warnings = state.get("security_warnings", [])
    if warnings:
        print(f"\n  Security warnings: {len(warnings)}")
        for w in warnings:
            print(f"    {w}")


def run_interactive(user_request: str, user_id: str) -> None:
    """Run the graph interactively (default mode)."""
    job_id = str(uuid.uuid4())[:8]

    print(f"\n{'='*60}")
    print(f"Multi-Agent Code Generator")
    print(f"{'='*60}")
    print(f"Request: {user_request}")
    print(f"Job ID:  {job_id}  |  User: {user_id}\n")

    initial_state: AgentState = {
        "job_id": job_id,
        "user_id": user_id,
        "user_request": user_request,
        "spec": "",
        "pages": [],
        "endpoints": [],
        "data_models": [],
        "fe_code": {},
        "be_code": {},
        "validation_passed": False,
        "validation_report": "",
        "validation_target": "",
        "current_agent": "",
        "retry_count": 0,
        "max_retries": 3,
        "total_tokens": 0,
        "token_budget": JOB_TOKEN_BUDGET,
        "error": "",
        "done": False,
        "cost_usd": 0.0,
        "cost_breakdown": {},
        "agent_tokens": {},
        "security_warnings": [],
    }

    graph = build_graph()

    print("Starting orchestrator loop...\n")
    start = time.time()

    step = 0
    final_state = initial_state
    for event in graph.stream(initial_state, {"recursion_limit": 25}):
        step += 1
        for node_name, state_update in event.items():
            current_agent = state_update.get("current_agent", "")
            tokens = state_update.get("total_tokens", 0)
            retries = state_update.get("retry_count", 0)
            error = state_update.get("error", "")

            status = f"  Step {step}: [{node_name}]"
            if current_agent:
                status += f" -> next: {current_agent}"
            if tokens:
                status += f" | tokens: {tokens:,}"
            if retries:
                status += f" | retries: {retries}"
            if error:
                status += f" | error: {error}"
            print(status)

            final_state = {**final_state, **state_update}

    elapsed = time.time() - start
    TOKENS_USED.inc(final_state.get("total_tokens", 0))
    COST_PER_PROJECT.observe(final_state.get("cost_usd", 0.0))
    JOB_DURATION.observe(elapsed)

    print(f"\n{'='*60}")
    print(f"Completed in {elapsed:.1f}s")
    print(f"Total tokens: {final_state.get('total_tokens', 0):,}")
    print(f"Total cost:   ${final_state.get('cost_usd', 0.0):.6f}")
    print(f"Retries: {final_state.get('retry_count', 0)}")
    print(f"Validation: {'PASSED' if final_state.get('validation_passed') else 'FAILED'}")
    _print_cost_summary(final_state)
    print(f"{'='*60}\n")

    write_artifacts(final_state)


def run_worker() -> None:
    """Run in stateless queue-worker mode."""
    from scaling.queue_worker import run_worker as start_worker

    graph = build_graph()
    start_worker(graph, write_artifacts)


def main():
    parser = argparse.ArgumentParser(description="Multi-Agent Code Generator")
    parser.add_argument("request", nargs="*", default=[], help="User request")
    parser.add_argument("--worker", action="store_true", help="Run as queue worker")
    parser.add_argument("--user-id", default="anonymous", help="User ID for rate limiting")
    args = parser.parse_args()

    # Start Prometheus metrics server
    start_metrics_server()

    if args.worker:
        run_worker()
    else:
        user_request = " ".join(args.request) if args.request else DEFAULT_REQUEST
        run_interactive(user_request, args.user_id)


if __name__ == "__main__":
    main()
