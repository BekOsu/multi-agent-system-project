# Multi-Agent Code Generator

A production-grade multi-agent system that generates full-stack applications (Next.js frontend + FastAPI backend) from natural language descriptions. Features security guardrails, cost controls, RAG context injection, stateless horizontal scaling, and deep observability.

## Architecture: Orchestrator Pattern

```
                    ┌──────────────┐
                    │ ORCHESTRATOR │ ← controls flow, retries, budget, rate limits
                    └──────┬───────┘
           ┌───────────────┼───────────────┐
           ▼               ▼               ▼
      ┌─────────┐   ┌──────────┐   ┌──────────┐
      │ PLANNER │   │ FE EXEC  │   │ BE EXEC  │
      └─────────┘   └──────────┘   └──────────┘
           ▲               ▲               ▲
           └───────────────┼───────────────┘
                    ┌──────┴───────┐
                    │  VALIDATOR   │ ← routes failures back
                    └──────────────┘
```

### Core Agents
- **Orchestrator** — inspects state, decides which agent runs next, enforces retry limits, token budgets, and per-agent cost caps
- **Planner** — creates the project spec (pages, endpoints, data models) with RAG-injected context from similar projects
- **FE Executor** — generates Next.js/React frontend code
- **BE Executor** — generates FastAPI backend code
- **Validator** — reviews all code against the spec, routes failures back to the responsible agent

## Production Features

### Security & Guardrails (`security/`)

Six security layers protect the system:

| Layer | Function | Purpose |
|-------|----------|---------|
| 1 | `verify_prompt_integrity()` | Hash system prompts at startup, verify before each call to detect tampering |
| 2 | `sanitize_input()` | Strip prompt injection patterns (`ignore previous`, `system:`, special tokens) |
| 3 | `validate_output()` | Parse agent output against Pydantic schemas, reject malformed responses |
| 4 | `check_tool_allowlist()` | Only `file_writer` permitted, reject unknown tool calls |
| 5 | `sandbox_file_path()` | Resolve paths, assert under `output/`, block path traversal (`../`, absolute paths) |
| 6 | `human_review_gate()` | Scan generated code for risky patterns (`eval`, `exec`, `subprocess`, `os.system`) |

Set `REQUIRE_HUMAN_REVIEW=true` to pause before writing artifacts when risky patterns are found.

### Cost Controls (`scaling/config.py`)

- **Per-agent token limits** — Each agent has a cumulative token cap (e.g., planner: 10K, executors: 30K each)
- **Job-level token budget** — 200K tokens total per run
- **Real-time cost tracking** — USD cost calculated per call using model pricing (input/output rates)
- **Cost breakdown** — Per-agent cost and token usage printed at end of run

```
Per-Agent Token Usage:
Agent                Tokens   Cost (USD)
----------------------------------------
orchestrator            850    $0.000638
planner               2,340    $0.001755
fe_executor           15,200    $0.011400
be_executor           12,800    $0.009600
validator              8,500    $0.006375
----------------------------------------
TOTAL                 39,690    $0.029768
```

### Stateless Workers & Horizontal Scaling (`scaling/`)

- **Queue Worker** (`queue_worker.py`) — SQS-based stateless worker loop
  - Workers are stateless: all state travels in the message body (AgentState serialized as JSON)
  - `LocalQueue` (in-memory deque) included for local demo without AWS
  - Graceful shutdown on SIGTERM
  - Exposes `queue_depth` Prometheus gauge for autoscaling (ASG/HPA)
- **Rate Limiter** (`rate_limiter.py`) — Sliding window per user_id
  - Configurable requests/minute and tokens/hour
  - In-memory for demo (swap Redis for production)

### RAG Context Injection (`rag/`)

- **Vector Store** (`vector_store.py`) — ChromaDB local persistent collection
  - Pre-loaded with example patterns: todo apps, e-commerce, auth, dashboards
  - Cosine similarity search for top-k relevant chunks
- **Context Injector** (`context_injector.py`) — Queries vector store, formats results as a context block
- **Planner integration** — Retrieved examples injected into the planner prompt before LLM call

### Observability

| Metric | Type | Labels | Purpose |
|--------|------|--------|---------|
| `agent_calls_total` | Counter | agent | Agent invocation count |
| `agent_errors_total` | Counter | agent | Parse/validation failures |
| `agent_token_usage` | Counter | agent | Per-agent token tracking |
| `agent_retries_total` | Counter | agent | Retry frequency |
| `rate_limit_rejections_total` | Counter | user_id | Rate limit hits |
| `cost_per_project_usd` | Histogram | — | Cost distribution |
| `job_duration_seconds` | Histogram | — | End-to-end latency |
| `agent_latency_seconds` | Histogram | agent | Per-agent call latency |
| `queue_depth` | Gauge | — | Job queue depth (scaling signal) |

**Langfuse** traces include `cost_usd`, `user_id`, `job_id` metadata per generation.

## Project Structure

```
multi-agent-demo/
├── main.py                         # Entry point (interactive + worker modes)
├── graph.py                        # LangGraph definition with guardrail middleware
├── state.py                        # Shared AgentState TypedDict
├── requirements.txt
├── .env.example
├── agents/
│   ├── orchestrator.py             # Routing + cost/rate-limit checks
│   ├── planner.py                  # Spec generation with RAG context
│   ├── fe_executor.py              # Frontend code generation
│   ├── be_executor.py              # Backend code generation
│   └── validator.py                # Code review + failure routing
├── security/
│   ├── guardrails.py               # 6 security layers
│   └── schemas.py                  # Pydantic output schemas
├── scaling/
│   ├── config.py                   # Token limits, pricing, rate-limit config
│   ├── rate_limiter.py             # Per-user sliding-window rate limiter
│   └── queue_worker.py             # SQS/local stateless queue worker
├── rag/
│   ├── vector_store.py             # ChromaDB vector store + seed examples
│   └── context_injector.py         # RAG → planner prompt injection
├── observability/
│   ├── metrics.py                  # Prometheus metrics (cost, queue, retries)
│   └── langfuse_tracer.py          # LLM tracing with cost/user metadata
├── prompts/
│   ├── orchestrator_prompt.py
│   ├── planner_prompt.py           # Includes {rag_context} placeholder
│   ├── fe_prompt.py
│   ├── be_prompt.py
│   └── validator_prompt.py
├── tools/
│   └── file_writer.py              # Sandboxed artifact writer with review gate
└── output/                         # Generated artifacts
```

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Configure API keys
cp .env.example .env
# Edit .env with your OpenAI key

# Run with default prompt
python main.py

# Run with custom prompt
python main.py "build an e-commerce site with cart and checkout"

# Run with user ID for rate limiting
python main.py --user-id user123 "build a blog with comments"

# Run in queue worker mode (local queue for demo)
python main.py --worker

# Enable human review gate for risky code patterns
REQUIRE_HUMAN_REVIEW=true python main.py
```

## Output

Generated code is written to `output/`:
- `output/frontend/` — Next.js pages and components
- `output/backend/` — FastAPI app and models
- `output/SPEC.md` — The planner's specification
- `output/VALIDATION_REPORT.md` — Validator's review

## Key Design Decisions

1. **LLM-driven routing** — Orchestrator uses an LLM call to decide the next agent, with deterministic fallback
2. **Validator routes failures** — returns a target agent for the Orchestrator to re-invoke
3. **Budget + retry caps** — stops after 3 retries or 200K tokens, with per-agent limits
4. **Graceful degradation** — Langfuse tracing is optional; metrics server is optional; ChromaDB is optional
5. **Stateless workers** — all state serialized in message body, enabling horizontal scaling
6. **Defense in depth** — 6 security layers from input sanitization to output validation to path sandboxing
7. **Cost transparency** — per-agent USD cost tracking with real-time model pricing
