"""Single place that classifies provider errors and defines the bounded recovery policy.

Every retry/split/failover decision in ``LLMClient`` and ``EntailmentEngine`` is
driven by ``classify_provider_error`` + ``RECOVERY_POLICY``; nothing else inspects
error strings. Each class has an explicit bounded retry count and next action.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum


class ErrorClass(StrEnum):
    AUTH = "auth"  # 401/403 permanent credential problem
    RATE_LIMIT = "rate_limit"  # 429 / TPM / RPM
    DAILY_QUOTA = "daily_quota"  # RPD/TPD exhausted for the day
    TIMEOUT = "timeout"
    SERVER = "server"  # 5xx / connection errors
    CONTEXT_LENGTH = "context_length"  # prompt too long / max_tokens truncation
    INVALID_OUTPUT = "invalid_output"  # JSON / schema validation failure
    CREDIT = "credit"  # 402 / insufficient balance
    NOT_FOUND = "not_found"  # model missing / unsupported request (permanent)
    UNKNOWN = "unknown"


class Action(StrEnum):
    RETRY = "retry"  # same provider, backoff
    SPLIT = "split"  # caller should split the batch (entailment only)
    FAILOVER = "failover"  # next provider in chain (own credentials)
    STOP = "stop"  # terminal for this request


@dataclass(frozen=True, slots=True)
class Policy:
    max_retries: int  # additional attempts on the same provider after the first
    on_exhausted: Action  # what to do when retries run out
    base_backoff: float  # seconds; exponential with jitter


# Bounded per-class policy. Totals are further capped by LLM_PROVIDER_MAX_ATTEMPTS
# and by the scan-wide BudgetGuard (every attempt reserves one unit first).
RECOVERY_POLICY: dict[ErrorClass, Policy] = {
    ErrorClass.AUTH: Policy(max_retries=0, on_exhausted=Action.FAILOVER, base_backoff=0.0),
    ErrorClass.NOT_FOUND: Policy(max_retries=0, on_exhausted=Action.FAILOVER, base_backoff=0.0),
    ErrorClass.CREDIT: Policy(max_retries=0, on_exhausted=Action.FAILOVER, base_backoff=0.0),
    ErrorClass.DAILY_QUOTA: Policy(max_retries=0, on_exhausted=Action.FAILOVER, base_backoff=0.0),
    ErrorClass.RATE_LIMIT: Policy(max_retries=2, on_exhausted=Action.FAILOVER, base_backoff=3.0),
    ErrorClass.TIMEOUT: Policy(max_retries=1, on_exhausted=Action.FAILOVER, base_backoff=2.0),
    ErrorClass.SERVER: Policy(max_retries=1, on_exhausted=Action.FAILOVER, base_backoff=2.0),
    ErrorClass.CONTEXT_LENGTH: Policy(max_retries=0, on_exhausted=Action.SPLIT, base_backoff=0.0),
    ErrorClass.INVALID_OUTPUT: Policy(max_retries=1, on_exhausted=Action.SPLIT, base_backoff=0.5),
    ErrorClass.UNKNOWN: Policy(max_retries=1, on_exhausted=Action.FAILOVER, base_backoff=1.0),
}

_RETRY_AFTER_TEXT_RE = re.compile(r"try again in (?:(\d+)m)?([\d\.]+)s", re.IGNORECASE)
_HTTP_RETRY_AFTER_RE = re.compile(r"(?i)retry-after['\"\s:=]+(\d+)")


@dataclass(frozen=True, slots=True)
class ClassifiedError:
    error_class: ErrorClass
    retry_after: float | None  # provider-advised wait, seconds
    status_code: int | None
    message: str  # sanitized by the caller

    @property
    def policy(self) -> Policy:
        return RECOVERY_POLICY[self.error_class]

    @property
    def permanent(self) -> bool:
        return self.error_class in (ErrorClass.AUTH, ErrorClass.NOT_FOUND)


def _status_code(exc: BaseException | None) -> int | None:
    if exc is None:
        return None
    for attr in ("status_code", "status", "code"):
        value = getattr(exc, attr, None)
        if isinstance(value, int) and 100 <= value <= 599:
            return value
    response = getattr(exc, "response", None)
    value = getattr(response, "status_code", None)
    if isinstance(value, int):
        return value
    return None


def parse_retry_after(text: str) -> float | None:
    m = _RETRY_AFTER_TEXT_RE.search(text)
    if m:
        mins = float(m.group(1)) if m.group(1) else 0.0
        secs = float(m.group(2)) if m.group(2) else 0.0
        return mins * 60.0 + secs
    m = _HTTP_RETRY_AFTER_RE.search(text)
    if m:
        return float(m.group(1))
    return None


def classify_provider_error(
    exc: BaseException | None,
    sanitized_message: str | None = None,
) -> ClassifiedError:
    """Classify a provider exception (or sanitized message) into an ErrorClass."""
    msg = (sanitized_message if sanitized_message is not None else str(exc or "")).strip()
    lower = msg.lower()
    code = _status_code(exc)
    retry_after = parse_retry_after(msg)

    if isinstance(exc, TimeoutError) or "timed out" in lower or "timeout" in lower:
        return ClassifiedError(ErrorClass.TIMEOUT, retry_after, code, msg)

    if code in (401, 403) or any(
        m in lower
        for m in (
            "invalid api key",
            "incorrect api key",
            "invalid_api_key",
            "authentication",
            "unauthorized",
            "permission_denied",
        )
    ):
        # Some providers return 403 for rate limits; keep those retryable.
        if "rate limit" in lower or "429" in lower:
            return ClassifiedError(ErrorClass.RATE_LIMIT, retry_after, code, msg)
        return ClassifiedError(ErrorClass.AUTH, None, code, msg)
    if "forbidden" in lower and "rate limit" not in lower:
        return ClassifiedError(ErrorClass.AUTH, None, code, msg)
    if " 401 " in f" {lower} " or lower.startswith("error code: 401"):
        return ClassifiedError(ErrorClass.AUTH, None, 401, msg)

    if code == 402 or any(
        m in lower
        for m in ("can only afford", "requires more credits", "insufficient_quota", "402")
    ):
        return ClassifiedError(ErrorClass.CREDIT, None, code or 402, msg)

    if any(
        m in lower
        for m in (
            "requests per day",
            "tokens per day",
            "generaterequestsperday",
            "daily limit",
            "quota exceeded",
            "resource_exhausted",
            "(rpd)",
            "(tpd)",
        )
    ):
        return ClassifiedError(ErrorClass.DAILY_QUOTA, retry_after, code, msg)

    if code == 429 or "rate limit" in lower or "429" in lower or "too many requests" in lower:
        return ClassifiedError(ErrorClass.RATE_LIMIT, retry_after, code or 429, msg)

    if any(
        m in lower
        for m in (
            "context_length",
            "context length",
            "maximum context",
            "prompt is too long",
            "max_tokens length limit",
            "reduce the length",
            "request too large",
            "too many tokens",
        )
    ):
        return ClassifiedError(ErrorClass.CONTEXT_LENGTH, None, code, msg)

    if any(
        m in lower
        for m in (
            "model_not_found",
            "does not exist",
            "model not found",
            "no longer available to new users",
            "is not found for api version",
        )
    ) or (
        code == 404
        and ("model" in lower or "models/" in lower or "not_found" in lower)
    ):
        return ClassifiedError(ErrorClass.NOT_FOUND, None, code or 404, msg)

    if (code is not None and code >= 500) or any(
        m in lower
        for m in (
            "500",
            "502",
            "503",
            "504",
            "internal server error",
            "bad gateway",
            "service unavailable",
            "connection error",
            "connection reset",
            "connection refused",
            "server disconnected",
        )
    ):
        return ClassifiedError(ErrorClass.SERVER, retry_after, code, msg)

    if any(
        m in lower
        for m in (
            "validation error",
            "validationerror",
            "failed to parse",
            "invalid json",
            "jsondecodeerror",
            "expecting value",
            "field required",
            "instructorretryexception",
            "json_validate_failed",
            "failed to generate json",
            "failed to validate json",
            "failed_generation",
        )
    ):
        return ClassifiedError(ErrorClass.INVALID_OUTPUT, None, code, msg)

    return ClassifiedError(ErrorClass.UNKNOWN, retry_after, code, msg)


class LLMProviderError(RuntimeError):
    """Typed provider failure carrying the classification (no secrets in message)."""

    def __init__(
        self,
        message: str,
        *,
        provider: str,
        model: str,
        error_class: ErrorClass,
        attempts: int = 1,
    ) -> None:
        self.provider = provider
        self.model = model
        self.error_class = error_class
        self.attempts = attempts
        self.reason = f"provider_{error_class.value}"
        super().__init__(message)


class LLMAuthError(LLMProviderError):
    """401/403: permanent; never retried with the same credential."""


__all__ = [
    "RECOVERY_POLICY",
    "Action",
    "ClassifiedError",
    "ErrorClass",
    "LLMAuthError",
    "LLMProviderError",
    "Policy",
    "classify_provider_error",
    "parse_retry_after",
]
