"""Frontend Executor agent — generates Next.js/React code."""

import json

from langchain_openai import ChatOpenAI

from prompts.fe_prompt import FE_HUMAN, FE_SYSTEM
from observability.langfuse_tracer import traced_call
from observability.metrics import AGENT_CALLS, AGENT_ERRORS
from scaling.config import calculate_cost
from scaling.rate_limiter import record_token_usage
from security.guardrails import validate_output
from state import AgentState


def run_fe_executor(state: AgentState) -> AgentState:
    AGENT_CALLS.labels(agent="fe_executor").inc()

    human_msg = FE_HUMAN.format(
        spec=state["spec"],
        pages=", ".join(state.get("pages", [])),
        endpoints=", ".join(state.get("endpoints", [])),
        data_models=", ".join(state.get("data_models", [])),
    )

    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.2)
    response = traced_call(
        llm, FE_SYSTEM, human_msg, agent_name="fe_executor",
        job_id=state.get("job_id", ""), user_id=state.get("user_id", ""),
    )

    input_tokens = response.usage_metadata.get("input_tokens", 0) if response.usage_metadata else 0
    output_tokens = response.usage_metadata.get("output_tokens", 0) if response.usage_metadata else 0
    tokens_used = input_tokens + output_tokens

    # Cost tracking
    call_cost = calculate_cost("gpt-4o-mini", input_tokens, output_tokens)
    cost_breakdown = dict(state.get("cost_breakdown", {}))
    cost_breakdown["fe_executor"] = cost_breakdown.get("fe_executor", 0.0) + call_cost
    agent_tokens = dict(state.get("agent_tokens", {}))
    agent_tokens["fe_executor"] = agent_tokens.get("fe_executor", 0) + tokens_used
    record_token_usage(state.get("user_id", "anonymous"), tokens_used)

    # Validate output with Pydantic schema
    valid, result = validate_output("fe_executor", response.content)
    if valid:
        fe_code = result.root if hasattr(result, "root") else json.loads(response.content)
        return {
            **state,
            "fe_code": fe_code,
            "total_tokens": state.get("total_tokens", 0) + tokens_used,
            "cost_usd": state.get("cost_usd", 0.0) + call_cost,
            "cost_breakdown": cost_breakdown,
            "agent_tokens": agent_tokens,
            "error": "",
        }
    else:
        AGENT_ERRORS.labels(agent="fe_executor").inc()
        return {
            **state,
            "total_tokens": state.get("total_tokens", 0) + tokens_used,
            "cost_usd": state.get("cost_usd", 0.0) + call_cost,
            "cost_breakdown": cost_breakdown,
            "agent_tokens": agent_tokens,
            "error": f"FE Executor output validation failed: {result}",
        }
