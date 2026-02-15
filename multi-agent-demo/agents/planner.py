"""Planner agent — creates the project specification and contract."""

import json

from langchain_openai import ChatOpenAI

from prompts.planner_prompt import PLANNER_HUMAN, PLANNER_SYSTEM
from observability.langfuse_tracer import traced_call
from observability.metrics import AGENT_CALLS, AGENT_ERRORS
from rag.context_injector import get_context
from scaling.config import calculate_cost
from scaling.rate_limiter import record_token_usage
from security.guardrails import validate_output
from state import AgentState


def run_planner(state: AgentState) -> AgentState:
    AGENT_CALLS.labels(agent="planner").inc()

    # RAG context injection
    rag_context = get_context(state["user_request"])

    human_msg = PLANNER_HUMAN.format(
        user_request=state["user_request"],
        rag_context=rag_context or "No reference examples available.",
    )

    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.2)
    response = traced_call(
        llm, PLANNER_SYSTEM, human_msg, agent_name="planner",
        job_id=state.get("job_id", ""), user_id=state.get("user_id", ""),
    )

    input_tokens = response.usage_metadata.get("input_tokens", 0) if response.usage_metadata else 0
    output_tokens = response.usage_metadata.get("output_tokens", 0) if response.usage_metadata else 0
    tokens_used = input_tokens + output_tokens

    # Cost tracking
    call_cost = calculate_cost("gpt-4o-mini", input_tokens, output_tokens)
    cost_breakdown = dict(state.get("cost_breakdown", {}))
    cost_breakdown["planner"] = cost_breakdown.get("planner", 0.0) + call_cost
    agent_tokens = dict(state.get("agent_tokens", {}))
    agent_tokens["planner"] = agent_tokens.get("planner", 0) + tokens_used
    record_token_usage(state.get("user_id", "anonymous"), tokens_used)

    # Validate output with Pydantic schema
    valid, result = validate_output("planner", response.content)
    if valid:
        plan = result.model_dump() if hasattr(result, "model_dump") else json.loads(response.content)
        return {
            **state,
            "spec": plan["spec"],
            "pages": plan["pages"],
            "endpoints": plan["endpoints"],
            "data_models": plan["data_models"],
            "total_tokens": state.get("total_tokens", 0) + tokens_used,
            "cost_usd": state.get("cost_usd", 0.0) + call_cost,
            "cost_breakdown": cost_breakdown,
            "agent_tokens": agent_tokens,
            "error": "",
        }
    else:
        AGENT_ERRORS.labels(agent="planner").inc()
        return {
            **state,
            "total_tokens": state.get("total_tokens", 0) + tokens_used,
            "cost_usd": state.get("cost_usd", 0.0) + call_cost,
            "cost_breakdown": cost_breakdown,
            "agent_tokens": agent_tokens,
            "error": f"Planner output validation failed: {result}",
        }
