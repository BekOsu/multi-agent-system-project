"""System-level metrics via Prometheus client."""

from prometheus_client import Counter, Gauge, Histogram, start_http_server

# Counters
AGENT_CALLS = Counter(
    "agent_calls_total",
    "Total number of agent invocations",
    ["agent"],
)

AGENT_ERRORS = Counter(
    "agent_errors_total",
    "Total number of agent errors (parse failures, etc.)",
    ["agent"],
)

TOKENS_USED = Counter(
    "tokens_used_total",
    "Total tokens consumed across all LLM calls",
)

AGENT_TOKEN_USAGE = Counter(
    "agent_token_usage",
    "Per-agent token tracking",
    ["agent"],
)

AGENT_RETRIES = Counter(
    "agent_retries_total",
    "Total number of agent retries",
    ["agent"],
)

RATE_LIMIT_REJECTIONS = Counter(
    "rate_limit_rejections_total",
    "Number of rate limit rejections",
    ["user_id"],
)

# Gauges
QUEUE_DEPTH = Gauge(
    "queue_depth",
    "Current depth of the job queue (scaling signal)",
)

# Histograms
AGENT_LATENCY = Histogram(
    "agent_latency_seconds",
    "Time spent in each agent call",
    ["agent"],
    buckets=[0.5, 1, 2, 5, 10, 30, 60],
)

COST_PER_PROJECT = Histogram(
    "cost_per_project_usd",
    "Cost distribution per project in USD",
    buckets=[0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0],
)

JOB_DURATION = Histogram(
    "job_duration_seconds",
    "End-to-end job latency",
    buckets=[5, 10, 30, 60, 120, 300, 600],
)


def start_metrics_server(port: int = 9090) -> None:
    """Start Prometheus metrics endpoint on /metrics."""
    try:
        start_http_server(port)
        print(f"[metrics] Prometheus metrics available at http://localhost:{port}/metrics")
    except OSError as e:
        print(f"[metrics] Could not start metrics server: {e}")
