"""Centralized configuration for token limits, cost controls, and rate limits."""

# Per-agent max token limits (cumulative across retries)
AGENT_TOKEN_LIMITS: dict[str, int] = {
    "orchestrator": 2_000,
    "planner": 10_000,
    "fe_executor": 30_000,
    "be_executor": 30_000,
    "validator": 15_000,
}

# Total token budget per job
JOB_TOKEN_BUDGET: int = 200_000

# Fallback model chain — tried in order on API errors
MODEL_CHAIN: list[str] = ["gpt-4o-mini", "gpt-4o", "gpt-3.5-turbo"]

# Model pricing per 1M tokens (USD)
MODEL_PRICING: dict[str, dict[str, float]] = {
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "gpt-3.5-turbo": {"input": 0.50, "output": 1.50},
}

# Rate-limit defaults (in-memory sliding window)
RATE_LIMIT_REQUESTS_PER_MINUTE: int = 10
RATE_LIMIT_TOKENS_PER_HOUR: int = 500_000


def calculate_cost(
    model: str, input_tokens: int, output_tokens: int
) -> float:
    """Return estimated cost in USD for a single LLM call."""
    pricing = MODEL_PRICING.get(model, {"input": 0.0, "output": 0.0})
    cost = (input_tokens * pricing["input"] + output_tokens * pricing["output"]) / 1_000_000
    return round(cost, 6)
