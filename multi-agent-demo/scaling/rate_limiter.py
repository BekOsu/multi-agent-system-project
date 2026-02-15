"""Per-user sliding-window rate limiter.

Uses in-memory storage for the demo. In production, swap for Redis
(e.g. redis.incr with TTL or a sorted-set sliding window).
"""

import time
from collections import defaultdict

from scaling.config import RATE_LIMIT_REQUESTS_PER_MINUTE, RATE_LIMIT_TOKENS_PER_HOUR

# In-memory stores
_request_timestamps: dict[str, list[float]] = defaultdict(list)
_token_usage: dict[str, list[tuple[float, int]]] = defaultdict(list)


def check_rate_limit(user_id: str) -> bool:
    """Return True if the user is within rate limits, False if exceeded."""
    now = time.time()

    # ── Requests-per-minute check ────────────────────────────────────────
    window_start = now - 60
    timestamps = _request_timestamps[user_id]
    # Prune old entries
    _request_timestamps[user_id] = [t for t in timestamps if t > window_start]
    if len(_request_timestamps[user_id]) >= RATE_LIMIT_REQUESTS_PER_MINUTE:
        return False
    _request_timestamps[user_id].append(now)

    return True


def record_token_usage(user_id: str, tokens: int) -> None:
    """Record token usage for per-hour tracking."""
    _token_usage[user_id].append((time.time(), tokens))


def check_token_rate_limit(user_id: str) -> bool:
    """Return True if the user is within the hourly token budget."""
    now = time.time()
    window_start = now - 3600
    entries = _token_usage[user_id]
    _token_usage[user_id] = [(t, n) for t, n in entries if t > window_start]
    total = sum(n for _, n in _token_usage[user_id])
    return total < RATE_LIMIT_TOKENS_PER_HOUR


def reset(user_id: str | None = None) -> None:
    """Reset rate-limit state. Pass None to reset all users."""
    if user_id is None:
        _request_timestamps.clear()
        _token_usage.clear()
    else:
        _request_timestamps.pop(user_id, None)
        _token_usage.pop(user_id, None)
