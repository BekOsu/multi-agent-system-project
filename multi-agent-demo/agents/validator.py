"""Validator agent — reviews code and routes failures back."""

import json

from langchain_openai import ChatOpenAI

from prompts.validator_prompt import VALIDATOR_HUMAN, VALIDATOR_SYSTEM
from observability.langfuse_tracer import traced_call
from observability.metrics import AGENT_CALLS, AGENT_ERRORS
from scaling.config import calculate_cost
from scaling.model_selector import get_model
from scaling.rate_limiter import record_token_usage
from security.guardrails import validate_output
from state import AgentState


def _format_code_block(code_dict: dict[str, str]) -> str:
    parts = []
    for filename, code in code_dict.items():
        parts.append(f"### {filename}\n```\n{code}\n```")
    return "\n\n".join(parts)


def run_validator(state: AgentState) -> AgentState:
    AGENT_CALLS.labels(agent="validator").inc()

    human_msg = VALIDATOR_HUMAN.format(
        spec=state["spec"],
        pages=", ".join(state.get("pages", [])),
        endpoints=", ".join(state.get("endpoints", [])),
        data_models=", ".join(state.get("data_models", [])),
        fe_code=_format_code_block(state.get("fe_code", {})),
        be_code=_format_code_block(state.get("be_code", {})),
    )

    model = get_model("validator")
    llm = ChatOpenAI(model=model, temperature=0)
    response = traced_call(
        llm, VALIDATOR_SYSTEM, human_msg, agent_name="validator",
        job_id=state.get("job_id", ""), user_id=state.get("user_id", ""),
    )

    model_used = getattr(response, "model_used", model)
    input_tokens = response.usage_metadata.get("input_tokens", 0) if response.usage_metadata else 0
    output_tokens = response.usage_metadata.get("output_tokens", 0) if response.usage_metadata else 0
    tokens_used = input_tokens + output_tokens

    # Cost tracking
    call_cost = calculate_cost(model_used, input_tokens, output_tokens)
    cost_breakdown = dict(state.get("cost_breakdown", {}))
    cost_breakdown["validator"] = cost_breakdown.get("validator", 0.0) + call_cost
    agent_tokens = dict(state.get("agent_tokens", {}))
    agent_tokens["validator"] = agent_tokens.get("validator", 0) + tokens_used
    record_token_usage(state.get("user_id", "anonymous"), tokens_used)

    # Validate output with Pydantic schema
    valid, parsed = validate_output("validator", response.content)
    if valid:
        result = parsed.model_dump() if hasattr(parsed, "model_dump") else json.loads(response.content)
        return {
            **state,
            "validation_passed": result["passed"],
            "validation_report": result["report"],
            "validation_target": result.get("target", ""),
            "total_tokens": state.get("total_tokens", 0) + tokens_used,
            "cost_usd": state.get("cost_usd", 0.0) + call_cost,
            "cost_breakdown": cost_breakdown,
            "agent_tokens": agent_tokens,
            "error": "",
        }
    else:
        AGENT_ERRORS.labels(agent="validator").inc()
        return {
            **state,
            "validation_passed": False,
            "validation_report": f"Validator output validation failed: {parsed}",
            "validation_target": "fe_executor",
            "total_tokens": state.get("total_tokens", 0) + tokens_used,
            "cost_usd": state.get("cost_usd", 0.0) + call_cost,
            "cost_breakdown": cost_breakdown,
            "agent_tokens": agent_tokens,
            "error": f"Validator output validation failed: {parsed}",
        }
