"""LLM-level tracing via Langfuse. Gracefully degrades if not configured."""

import os
import time

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage

from scaling.config import calculate_cost

_langfuse = None


def _get_langfuse():
    global _langfuse
    if _langfuse is not None:
        return _langfuse
    try:
        from langfuse import Langfuse
        if os.getenv("LANGFUSE_PUBLIC_KEY"):
            _langfuse = Langfuse()
            print("[langfuse] Tracing enabled")
        else:
            _langfuse = False
            print("[langfuse] No API key found — tracing disabled")
    except ImportError:
        _langfuse = False
        print("[langfuse] Package not installed — tracing disabled")
    return _langfuse


def traced_call(
    llm: ChatOpenAI,
    system_prompt: str,
    human_prompt: str,
    agent_name: str,
    job_id: str = "",
    user_id: str = "",
):
    """Call the LLM and trace via Langfuse if available."""
    messages = [SystemMessage(content=system_prompt), HumanMessage(content=human_prompt)]

    lf = _get_langfuse()
    if not lf:
        return llm.invoke(messages)

    trace = lf.trace(
        name=f"agent-{agent_name}",
        metadata={
            "job_id": job_id,
            "user_id": user_id,
            "agent": agent_name,
        },
        user_id=user_id or None,
        session_id=job_id or None,
    )
    generation = trace.generation(
        name=f"{agent_name}-llm-call",
        model=llm.model_name,
        input={"system": system_prompt, "human": human_prompt},
    )

    start = time.time()
    response = llm.invoke(messages)
    duration_ms = (time.time() - start) * 1000

    input_tokens = response.usage_metadata.get("input_tokens", 0) if response.usage_metadata else 0
    output_tokens = response.usage_metadata.get("output_tokens", 0) if response.usage_metadata else 0
    total_tokens = response.usage_metadata.get("total_tokens", 0) if response.usage_metadata else 0
    cost_usd = calculate_cost("gpt-4o-mini", input_tokens, output_tokens)

    generation.end(
        output=response.content,
        usage={
            "input": input_tokens,
            "output": output_tokens,
            "total": total_tokens,
        },
        metadata={
            "duration_ms": round(duration_ms, 2),
            "cost_usd": cost_usd,
            "job_id": job_id,
            "user_id": user_id,
        },
    )
    lf.flush()
    return response
