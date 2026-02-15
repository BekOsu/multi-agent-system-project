"""Backend Executor agent — generates FastAPI code."""

import json

from langchain_openai import ChatOpenAI

from prompts.be_prompt import BE_HUMAN, BE_SYSTEM
from observability.langfuse_tracer import traced_call
from observability.metrics import AGENT_CALLS, AGENT_ERRORS
from scaling.config import calculate_cost
from scaling.model_selector import get_model
from scaling.rate_limiter import record_token_usage
from security.guardrails import validate_output
from state import AgentState


def run_be_executor(state: AgentState) -> AgentState:
    AGENT_CALLS.labels(agent="be_executor").inc()

    human_msg = BE_HUMAN.format(
        spec=state["spec"],
        endpoints=", ".join(state.get("endpoints", [])),
        data_models=", ".join(state.get("data_models", [])),
    )

    model = get_model("be_executor")
    llm = ChatOpenAI(model=model, temperature=0.2)
    response = traced_call(
        llm, BE_SYSTEM, human_msg, agent_name="be_executor",
        job_id=state.get("job_id", ""), user_id=state.get("user_id", ""),
    )

    model_used = getattr(response, "model_used", model)
    input_tokens = response.usage_metadata.get("input_tokens", 0) if response.usage_metadata else 0
    output_tokens = response.usage_metadata.get("output_tokens", 0) if response.usage_metadata else 0
    tokens_used = input_tokens + output_tokens

    # Cost tracking
    call_cost = calculate_cost(model_used, input_tokens, output_tokens)
    cost_breakdown = dict(state.get("cost_breakdown", {}))
    cost_breakdown["be_executor"] = cost_breakdown.get("be_executor", 0.0) + call_cost
    agent_tokens = dict(state.get("agent_tokens", {}))
    agent_tokens["be_executor"] = agent_tokens.get("be_executor", 0) + tokens_used
    record_token_usage(state.get("user_id", "anonymous"), tokens_used)

    # Validate output with Pydantic schema
    valid, result = validate_output("be_executor", response.content)
    if valid:
        be_code = result.root if hasattr(result, "root") else json.loads(response.content)
        return {
            **state,
            "be_code": be_code,
            "total_tokens": state.get("total_tokens", 0) + tokens_used,
            "cost_usd": state.get("cost_usd", 0.0) + call_cost,
            "cost_breakdown": cost_breakdown,
            "agent_tokens": agent_tokens,
            "error": "",
        }
    else:
        AGENT_ERRORS.labels(agent="be_executor").inc()
        return {
            **state,
            "total_tokens": state.get("total_tokens", 0) + tokens_used,
            "cost_usd": state.get("cost_usd", 0.0) + call_cost,
            "cost_breakdown": cost_breakdown,
            "agent_tokens": agent_tokens,
            "error": f"BE Executor output validation failed: {result}",
        }
