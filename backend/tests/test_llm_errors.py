"""Classifier + recovery policy: 401 is permanent; 429 is bounded-retry."""

from __future__ import annotations

from app.core.llm_errors import (
    Action,
    ErrorClass,
    classify_provider_error,
    parse_retry_after,
)


class _HttpErr(RuntimeError):
    def __init__(self, message: str, status_code: int) -> None:
        self.status_code = status_code
        super().__init__(message)


def test_401_is_auth_permanent_no_retry() -> None:
    ce = classify_provider_error(_HttpErr("Error code: 401 - Invalid API Key", 401))
    assert ce.error_class is ErrorClass.AUTH
    assert ce.status_code == 401
    assert ce.permanent is True
    assert ce.policy.max_retries == 0
    assert ce.policy.on_exhausted is Action.FAILOVER


def test_403_without_rate_limit_is_auth() -> None:
    ce = classify_provider_error(_HttpErr("forbidden", 403))
    assert ce.error_class is ErrorClass.AUTH
    assert ce.permanent is True


def test_429_is_rate_limit_with_retry_after() -> None:
    msg = "Rate limit reached. Please try again in 1m2.5s"
    ce = classify_provider_error(_HttpErr(msg, 429), msg)
    assert ce.error_class is ErrorClass.RATE_LIMIT
    assert ce.permanent is False
    assert ce.policy.max_retries == 2
    assert ce.policy.on_exhausted is Action.FAILOVER
    assert ce.retry_after == 62.5


def test_parse_retry_after_from_header_text() -> None:
    assert parse_retry_after("retry-after: 12") == 12.0
    assert parse_retry_after("try again in 7.5s") == 7.5
    assert parse_retry_after("no hint") is None


def test_daily_quota_is_not_retried() -> None:
    ce = classify_provider_error(RuntimeError("requests per day (RPD) exceeded"))
    assert ce.error_class is ErrorClass.DAILY_QUOTA
    assert ce.policy.max_retries == 0


def test_context_length_asks_for_split() -> None:
    ce = classify_provider_error(RuntimeError("This model's maximum context length is 8192 tokens"))
    assert ce.error_class is ErrorClass.CONTEXT_LENGTH
    assert ce.policy.on_exhausted is Action.SPLIT
    assert ce.policy.max_retries == 0


def test_credit_exhausted_is_terminal_for_provider() -> None:
    ce = classify_provider_error(_HttpErr("You can only afford 0 tokens", 402))
    assert ce.error_class is ErrorClass.CREDIT
    assert ce.policy.max_retries == 0


def test_groq_json_validate_failed_is_invalid_output() -> None:
    msg = (
        "Error code: 400 - {'error': {'message': \"Failed to generate JSON. "
        "Please adjust your prompt. See 'failed_generation' for more details.\", "
        "'type': 'invalid_request_error', 'code': 'json_validate_failed'}}"
    )
    ce = classify_provider_error(RuntimeError(msg), msg)
    assert ce.error_class is ErrorClass.INVALID_OUTPUT
    assert ce.policy.max_retries == 1


def test_connection_error_is_server_class() -> None:
    ce = classify_provider_error(RuntimeError("Connection error."))
    assert ce.error_class is ErrorClass.SERVER
    assert ce.policy.max_retries == 1
    assert ce.policy.on_exhausted is Action.FAILOVER
