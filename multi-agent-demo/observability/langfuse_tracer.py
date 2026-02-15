"""LLM-level tracing via Langfuse. Gracefully degrades if not configured.

Includes retry logic with fallback model chain on API errors.
"""

import logging
import os
import time

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage

from scaling.config import MODEL_CHAIN, calculate_cost
from scaling.model_selector import get_model

logger = logging.getLogger(__name__)

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
    """Call the LLM and trace via Langfuse if available.

    On API errors (rate limit, model unavailable), retries with the next
    model in MODEL_CHAIN. Max 3 attempts across the chain.
    """
    messages = [SystemMessage(content=system_prompt), HumanMessage(content=human_prompt)]
    max_attempts = min(len(MODEL_CHAIN), 3)
    last_error = None
    model_used = llm.model_name

    for attempt in range(max_attempts):
        if attempt > 0:
            model_used = get_model(agent_name, attempt=attempt)
            llm = ChatOpenAI(model=model_used, temperature=llm.temperature)
            logger.warning(
                f"[langfuse] {agent_name}: retrying with fallback model '{model_used}' "
                f"(attempt {attempt + 1}/{max_attempts})"
            )

        try:
            response = _traced_invoke(
                llm, messages, system_prompt, human_prompt,
                agent_name, job_id, user_id, model_used,
            )
            response.model_used = model_used
            return response
        except Exception as e:
            last_error = e
            logger.error(f"[langfuse] {agent_name}: API error on '{model_used}': {e}")
            if attempt == max_attempts - 1:
                raise last_error


def _traced_invoke(
    llm, messages, system_prompt, human_prompt,
    agent_name, job_id, user_id, model_used,
):
    """Invoke LLM with optional Langfuse tracing."""
    lf = _get_langfuse()
    if not lf:
        return llm.invoke(messages)

    trace = lf.trace(
        name=f"agent-{agent_name}",
        metadata={
            "job_id": job_id,
            "user_id": user_id,
            "agent": agent_name,
            "model": model_used,
        },
        user_id=user_id or None,
        session_id=job_id or None,
    )
    generation = trace.generation(
        name=f"{agent_name}-llm-call",
        model=model_used,
        input={"system": system_prompt, "human": human_prompt},
    )

    start = time.time()
    response = llm.invoke(messages)
    duration_ms = (time.time() - start) * 1000

    input_tokens = response.usage_metadata.get("input_tokens", 0) if response.usage_metadata else 0
    output_tokens = response.usage_metadata.get("output_tokens", 0) if response.usage_metadata else 0
    total_tokens = response.usage_metadata.get("total_tokens", 0) if response.usage_metadata else 0
    cost_usd = calculate_cost(model_used, input_tokens, output_tokens)

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
            "model_used": model_used,
            "job_id": job_id,
            "user_id": user_id,
        },
    )
    lf.flush()
    return response
