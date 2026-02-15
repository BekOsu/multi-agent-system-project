"""Orchestrator agent — decides which agent runs next."""

import json

from langchain_openai import ChatOpenAI

from prompts.orchestrator_prompt import ORCHESTRATOR_HUMAN, ORCHESTRATOR_SYSTEM
from observability.langfuse_tracer import traced_call
from observability.metrics import AGENT_CALLS, AGENT_ERRORS, AGENT_RETRIES
from scaling.config import AGENT_TOKEN_LIMITS, calculate_cost
from scaling.rate_limiter import check_rate_limit, record_token_usage
from state import AgentState


def run_orchestrator(state: AgentState) -> AgentState:
    """Inspect state and decide the next agent to run."""
    AGENT_CALLS.labels(agent="orchestrator").inc()

    # Rate-limit check
    user_id = state.get("user_id", "anonymous")
    if not check_rate_limit(user_id):
        return {**state, "current_agent": "done", "done": True,
                "error": "Rate limit exceeded"}

    # Hard stop checks
    if state.get("retry_count", 0) >= state.get("max_retries", 3):
        return {**state, "current_agent": "done", "done": True,
                "error": "Max retries exceeded"}
    if state.get("total_tokens", 0) >= state.get("token_budget", 200_000):
        return {**state, "current_agent": "done", "done": True,
                "error": "Token budget exceeded"}
    if state.get("validation_passed"):
        return {**state, "current_agent": "done", "done": True}

    human_msg = ORCHESTRATOR_HUMAN.format(
        user_request=state.get("user_request", ""),
        has_spec=bool(state.get("spec")),
        fe_file_count=len(state.get("fe_code", {})),
        be_file_count=len(state.get("be_code", {})),
        validation_passed=state.get("validation_passed", False),
        validation_target=state.get("validation_target", ""),
        retry_count=state.get("retry_count", 0),
        max_retries=state.get("max_retries", 3),
        total_tokens=state.get("total_tokens", 0),
        token_budget=state.get("token_budget", 200_000),
        error=state.get("error", ""),
    )

    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    response = traced_call(
        llm, ORCHESTRATOR_SYSTEM, human_msg, agent_name="orchestrator",
        job_id=state.get("job_id", ""), user_id=user_id,
    )

    input_tokens = response.usage_metadata.get("input_tokens", 0) if response.usage_metadata else 0
    output_tokens = response.usage_metadata.get("output_tokens", 0) if response.usage_metadata else 0
    tokens_used = input_tokens + output_tokens

    # Cost tracking
    call_cost = calculate_cost("gpt-4o-mini", input_tokens, output_tokens)
    cost_breakdown = dict(state.get("cost_breakdown", {}))
    cost_breakdown["orchestrator"] = cost_breakdown.get("orchestrator", 0.0) + call_cost
    agent_tokens = dict(state.get("agent_tokens", {}))
    agent_tokens["orchestrator"] = agent_tokens.get("orchestrator", 0) + tokens_used
    record_token_usage(user_id, tokens_used)

    try:
        decision = json.loads(response.content)
        next_agent = decision["next_agent"]
    except (json.JSONDecodeError, KeyError):
        AGENT_ERRORS.labels(agent="orchestrator").inc()
        next_agent = _fallback_routing(state)

    # Per-agent token limit check: if the target agent exceeded its limit, skip to done
    agent_limit = AGENT_TOKEN_LIMITS.get(next_agent, float("inf"))
    if agent_tokens.get(next_agent, 0) >= agent_limit:
        next_agent = "done"

    new_state = {
        **state,
        "current_agent": next_agent,
        "total_tokens": state.get("total_tokens", 0) + tokens_used,
        "cost_usd": state.get("cost_usd", 0.0) + call_cost,
        "cost_breakdown": cost_breakdown,
        "agent_tokens": agent_tokens,
        "done": next_agent == "done",
    }

    # If routing back after validation failure, bump retry count
    if state.get("validation_target") and next_agent in (
        "planner", "fe_executor", "be_executor"
    ):
        new_state["retry_count"] = state.get("retry_count", 0) + 1
        new_state["validation_target"] = ""
        AGENT_RETRIES.labels(agent=next_agent).inc()

    return new_state


def _fallback_routing(state: AgentState) -> str:
    """Deterministic fallback when LLM response is unparseable."""
    if not state.get("spec"):
        return "planner"
    if not state.get("fe_code"):
        return "fe_executor"
    if not state.get("be_code"):
        return "be_executor"
    if not state.get("validation_passed") and state.get("fe_code") and state.get("be_code"):
        return "validator"
    return "done"
