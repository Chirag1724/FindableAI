"""Failure classification and safe error redaction for durable jobs."""

from __future__ import annotations

import re
from enum import StrEnum

_SECRET_KV = re.compile(
    r"(?i)\b(api[_-]?key|token|authorization|bearer|secret)\b\s*[:=]\s*\S+"
)
_SECRET_LITERALS = (
    re.compile(r"(?i)gsk_[A-Za-z0-9]+"),
    re.compile(r"(?i)ghp_[A-Za-z0-9]+"),
    re.compile(r"(?i)sk-[A-Za-z0-9]{20,}"),
    re.compile(r"(?i)Bearer\s+\S+"),
)


class FailureCategory(StrEnum):
    RETRYABLE = "retryable"
    PERMANENT = "permanent"
    BUDGET_EXHAUSTED = "budget_exhausted"
    CANCELLED = "cancelled"
    PROVIDER = "provider"
    DATABASE = "database"
    GITHUB = "github"
    TIMEOUT = "timeout"
    UNKNOWN = "unknown"


class JobErrorCode(StrEnum):
    RETRYABLE = "retryable_error"
    PERMANENT = "permanent_error"
    BUDGET_EXHAUSTED = "budget_exhausted"
    CANCELLED = "cancelled"
    PROVIDER_AUTH = "provider_auth"
    PROVIDER_RATE_LIMIT = "provider_rate_limit"
    PROVIDER_TIMEOUT = "provider_timeout"
    DATABASE = "database_error"
    GITHUB_TIMEOUT = "github_timeout"
    GITHUB_ERROR = "github_error"
    EXECUTION_DEADLINE = "execution_deadline"
    STALE_FENCE = "stale_fence"
    UNKNOWN = "unknown_error"


_PERMANENT_MARKERS = (
    "invalid api key",
    "incorrect api key",
    "authentication",
    "unauthorized",
    "forbidden",
    "401",
    "403",
    "invalid_request",
    "validation error",
    "ssrf",
    "security rejection",
    "malformed",
)

_RETRYABLE_MARKERS = (
    "timeout",
    "timed out",
    "temporarily unavailable",
    "connection reset",
    "connection refused",
    "broken pipe",
    "rate limit",
    "429",
    "502",
    "503",
    "504",
    "econnreset",
    "server disconnected",
)


def redact_error(text: str | None, *, max_len: int = 500) -> str:
    if not text:
        return ""
    sanitized = str(text)
    sanitized = _SECRET_KV.sub(r"\1=***REDACTED***", sanitized)
    for pattern in _SECRET_LITERALS:
        sanitized = pattern.sub("***REDACTED***", sanitized)
    sanitized = sanitized.replace("\n", " ").strip()
    if len(sanitized) > max_len:
        return sanitized[: max_len - 3] + "..."
    return sanitized


def classify_failure(exc: BaseException | str) -> tuple[FailureCategory, JobErrorCode, bool]:
    """Return (category, code, is_retryable)."""
    msg = redact_error(str(exc)).lower()

    if "budget" in msg and ("exhaust" in msg or "exceed" in msg):
        return FailureCategory.BUDGET_EXHAUSTED, JobErrorCode.BUDGET_EXHAUSTED, False

    if "cancel" in msg:
        return FailureCategory.CANCELLED, JobErrorCode.CANCELLED, False

    if "already failed" in msg or "skipping re-execution" in msg:
        return FailureCategory.PERMANENT, JobErrorCode.PERMANENT, False

    if any(m in msg for m in _PERMANENT_MARKERS):
        if "rate limit" in msg or "429" in msg:
            return FailureCategory.RETRYABLE, JobErrorCode.PROVIDER_RATE_LIMIT, True
        if "401" in msg or "403" in msg or "api key" in msg or "unauthorized" in msg:
            return FailureCategory.PERMANENT, JobErrorCode.PROVIDER_AUTH, False
        return FailureCategory.PERMANENT, JobErrorCode.PERMANENT, False

    if "github" in msg:
        if "timeout" in msg or "timed out" in msg:
            return FailureCategory.TIMEOUT, JobErrorCode.GITHUB_TIMEOUT, True
        return FailureCategory.GITHUB, JobErrorCode.GITHUB_ERROR, True

    if any(m in msg for m in ("database", "operationalerror", "connection does not exist")):
        return FailureCategory.DATABASE, JobErrorCode.DATABASE, True

    if any(m in msg for m in _RETRYABLE_MARKERS):
        if "timeout" in msg or "timed out" in msg:
            return FailureCategory.TIMEOUT, JobErrorCode.PROVIDER_TIMEOUT, True
        if "rate limit" in msg or "429" in msg:
            return FailureCategory.RETRYABLE, JobErrorCode.PROVIDER_RATE_LIMIT, True
        return FailureCategory.RETRYABLE, JobErrorCode.RETRYABLE, True

    return FailureCategory.UNKNOWN, JobErrorCode.UNKNOWN, True
