"""Stateless queue worker for horizontal scaling.

Supports two backends:
- **LocalQueue**: In-memory deque for demo / local development.
- **SQSQueue**: AWS SQS for production (requires boto3 + SQS_QUEUE_URL env var).

Workers are stateless — all job state travels in the message body as serialized
JSON (AgentState). An autoscaler (ASG / HPA) can watch the `queue_depth`
Prometheus gauge to add or remove workers.
"""

import json
import os
import signal
import time
from collections import deque

from observability.metrics import QUEUE_DEPTH

# ── Local in-memory queue (demo mode) ───────────────────────────────────────


class LocalQueue:
    """Thread-safe-ish in-memory queue that mimics the SQS interface."""

    def __init__(self):
        self._q: deque[str] = deque()

    def send_message(self, body: str) -> None:
        self._q.append(body)
        QUEUE_DEPTH.set(len(self._q))

    def receive_message(self, wait_seconds: int = 1) -> str | None:
        """Block up to *wait_seconds*, return message body or None."""
        deadline = time.time() + wait_seconds
        while time.time() < deadline:
            if self._q:
                msg = self._q.popleft()
                QUEUE_DEPTH.set(len(self._q))
                return msg
            time.sleep(0.1)
        return None

    def delete_message(self, _receipt: str | None = None) -> None:
        """No-op for local queue (message already removed on receive)."""
        pass

    @property
    def depth(self) -> int:
        return len(self._q)


# ── SQS queue (production) ──────────────────────────────────────────────────


class SQSQueue:
    """Thin wrapper around boto3 SQS. Requires SQS_QUEUE_URL env var."""

    def __init__(self):
        import boto3

        self._url = os.environ["SQS_QUEUE_URL"]
        self._client = boto3.client("sqs")

    def send_message(self, body: str) -> None:
        self._client.send_message(QueueUrl=self._url, MessageBody=body)

    def receive_message(self, wait_seconds: int = 10) -> tuple[str | None, str | None]:
        """Return (body, receipt_handle) or (None, None)."""
        resp = self._client.receive_message(
            QueueUrl=self._url,
            MaxNumberOfMessages=1,
            WaitTimeSeconds=wait_seconds,
        )
        messages = resp.get("Messages", [])
        if not messages:
            return None, None
        msg = messages[0]
        return msg["Body"], msg["ReceiptHandle"]

    def delete_message(self, receipt_handle: str) -> None:
        self._client.delete_message(
            QueueUrl=self._url, ReceiptHandle=receipt_handle
        )


# ── Worker loop ──────────────────────────────────────────────────────────────

_running = True


def _handle_sigterm(*_):
    global _running
    print("[worker] SIGTERM received — shutting down gracefully")
    _running = False


def run_worker(graph, write_fn) -> None:
    """Poll the queue and process jobs until SIGTERM.

    Args:
        graph: Compiled LangGraph to invoke per job.
        write_fn: Callable(state) to persist output artifacts.
    """
    signal.signal(signal.SIGTERM, _handle_sigterm)

    use_sqs = bool(os.getenv("SQS_QUEUE_URL"))
    queue = SQSQueue() if use_sqs else LocalQueue()
    backend = "SQS" if use_sqs else "local"
    print(f"[worker] Started ({backend} backend). Waiting for jobs…")

    while _running:
        if use_sqs:
            body, receipt = queue.receive_message(wait_seconds=10)
        else:
            body = queue.receive_message(wait_seconds=2)
            receipt = None

        if body is None:
            continue

        print(f"[worker] Processing job…")
        try:
            initial_state = json.loads(body)
            final_state = initial_state
            for event in graph.stream(initial_state, {"recursion_limit": 25}):
                for _node, update in event.items():
                    final_state = {**final_state, **update}

            write_fn(final_state)
            print(f"[worker] Job complete.")
        except Exception as exc:
            print(f"[worker] Job failed: {exc}")
        finally:
            if receipt:
                queue.delete_message(receipt)

    print("[worker] Stopped.")
