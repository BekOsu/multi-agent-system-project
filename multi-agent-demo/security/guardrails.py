"""Six-layer security guardrails for the multi-agent system."""

import hashlib
import os
import re
from pathlib import Path

from pydantic import ValidationError

from security.schemas import (
    BEExecutorOutput,
    FEExecutorOutput,
    PlannerOutput,
    ValidatorOutput,
)

# ── Layer 1: Prompt integrity ────────────────────────────────────────────────

_prompt_hashes: dict[str, str] = {}


def register_prompt(name: str, text: str) -> None:
    """Hash a system prompt at startup for tamper detection."""
    _prompt_hashes[name] = hashlib.sha256(text.encode()).hexdigest()


def verify_prompt_integrity(name: str, text: str) -> bool:
    """Return True if the prompt matches its registered hash."""
    expected = _prompt_hashes.get(name)
    if expected is None:
        return True  # not registered — skip check
    return hashlib.sha256(text.encode()).hexdigest() == expected


# ── Layer 2: Input sanitization ──────────────────────────────────────────────

_INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(all\s+)?previous\s+instructions", re.IGNORECASE),
    re.compile(r"system\s*:", re.IGNORECASE),
    re.compile(r"<\|im_start\|>", re.IGNORECASE),
    re.compile(r"<\|im_end\|>", re.IGNORECASE),
    re.compile(r"<\|endoftext\|>", re.IGNORECASE),
    re.compile(r"```\s*system", re.IGNORECASE),
]


def sanitize_input(text: str) -> str:
    """Strip known prompt-injection patterns from user input."""
    sanitized = text
    for pattern in _INJECTION_PATTERNS:
        sanitized = pattern.sub("[REDACTED]", sanitized)
    return sanitized


# ── Layer 3: Output validation ───────────────────────────────────────────────

_SCHEMA_MAP = {
    "planner": PlannerOutput,
    "fe_executor": FEExecutorOutput,
    "be_executor": BEExecutorOutput,
    "validator": ValidatorOutput,
}


def validate_output(agent_name: str, raw_json: str) -> tuple[bool, object | str]:
    """Parse raw JSON against the Pydantic schema for *agent_name*.

    Returns (True, parsed_model) on success, (False, error_string) on failure.
    """
    schema = _SCHEMA_MAP.get(agent_name)
    if schema is None:
        return True, raw_json  # no schema registered — pass through

    try:
        model = schema.model_validate_json(raw_json)
        return True, model
    except (ValidationError, ValueError) as exc:
        return False, str(exc)


# ── Layer 4: Tool allowlist ──────────────────────────────────────────────────

_ALLOWED_TOOLS = {"file_writer"}


def check_tool_allowlist(tool_name: str) -> bool:
    """Return True if the tool is permitted."""
    return tool_name in _ALLOWED_TOOLS


# ── Layer 5: Path sandboxing ────────────────────────────────────────────────

_SANDBOX_ROOT = Path(__file__).resolve().parent.parent / "output"


def sandbox_file_path(filepath: str) -> Path:
    """Resolve *filepath* and assert it falls under the output/ directory.

    Raises ValueError on path-traversal attempts.
    """
    resolved = (_SANDBOX_ROOT / filepath).resolve()
    if not str(resolved).startswith(str(_SANDBOX_ROOT.resolve())):
        raise ValueError(
            f"Path traversal blocked: {filepath!r} resolves outside output/"
        )
    return resolved


# ── Layer 6: Human-review gate ───────────────────────────────────────────────

_RISKY_PATTERNS = [
    re.compile(r"\beval\s*\("),
    re.compile(r"\bexec\s*\("),
    re.compile(r"\bsubprocess\b"),
    re.compile(r"\bos\.system\s*\("),
    re.compile(r"\b__import__\s*\("),
]


def human_review_gate(code_artifacts: dict[str, str]) -> list[str]:
    """Scan generated code for risky patterns.

    Returns a list of warnings. If REQUIRE_HUMAN_REVIEW=true, callers should
    pause and display these before writing artifacts.
    """
    warnings: list[str] = []
    for filename, code in code_artifacts.items():
        for pattern in _RISKY_PATTERNS:
            if pattern.search(code):
                warnings.append(
                    f"[security] Risky pattern {pattern.pattern!r} found in {filename}"
                )
    return warnings


def require_human_review() -> bool:
    """Return True if the REQUIRE_HUMAN_REVIEW env var is set to true."""
    return os.getenv("REQUIRE_HUMAN_REVIEW", "").lower() == "true"
