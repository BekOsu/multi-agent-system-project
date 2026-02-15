"""Shared agent state flowing through the LangGraph graph."""

from typing import TypedDict


class AgentState(TypedDict, total=False):
    # Job identity
    job_id: str  # unique per run
    user_id: str  # for rate limiting / tracing
    user_request: str
    # Planner outputs
    spec: str  # The full specification / contract
    pages: list[str]  # Frontend page names
    endpoints: list[str]  # Backend endpoint names
    data_models: list[str]  # Data model names
    # Executor outputs
    fe_code: dict[str, str]  # filename -> code
    be_code: dict[str, str]  # filename -> code
    # Validator outputs
    validation_passed: bool
    validation_report: str
    validation_target: str  # "planner" | "fe_executor" | "be_executor" | ""
    # Orchestrator tracking
    current_agent: str
    retry_count: int
    max_retries: int
    total_tokens: int
    token_budget: int
    error: str
    done: bool
    # Cost tracking
    cost_usd: float  # running total
    cost_breakdown: dict[str, float]  # per-agent cost in USD
    # Per-agent token tracking
    agent_tokens: dict[str, int]  # per-agent cumulative tokens
    # Model selection
    model_used: str  # last model used for LLM call
    job_status: str  # "pending" | "running" | "completed" | "failed"
    # Security
    security_warnings: list[str]
