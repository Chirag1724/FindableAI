"""Shared async LLM client with Instructor structured outputs and call budget."""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from typing import Any, TypeVar

from pydantic import BaseModel

from app.core.budget import BudgetExhausted, BudgetGuard, LLMBudgetExceededError
from app.core.config import settings

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

_REDACTED = "***REDACTED***"

# Re-export for existing imports: ``from app.core.llm import BudgetExhausted``.
__all__ = [
    "BudgetExhausted",
    "BudgetGuard",
    "LLMBudgetExceededError",
    "LLMClient",
]


def _sanitize_text(text: str, secrets: Sequence[str]) -> str:
    sanitized = text
    for secret in secrets:
        if secret and secret in sanitized:
            sanitized = sanitized.replace(secret, _REDACTED)
    return sanitized


class LLMClient:
    """
    Single reusable async client for structured LLM calls.

    Engines must use this class instead of constructing Groq/LiteLLM clients
    directly. The provider transport is LiteLLM + Instructor so models remain
    replaceable via ``DEFAULT_LLM_MODEL`` (e.g. ``groq/…``, ``openai/…``).

    Call accounting is delegated to a scan-scoped ``BudgetGuard``. Multiple
    ``LLMClient`` instances may share one guard so the hard cap is global
    per scan, not per client instance.
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        max_calls: int | None = None,
        budget_cap_usd: float | None = None,
        budget_guard: BudgetGuard | None = None,
        instructor_client: Any | None = None,
    ) -> None:
        self._api_key = settings.GROQ_API_KEY if api_key is None else api_key
        self._model = model or settings.DEFAULT_LLM_MODEL

        if budget_guard is not None:
            if max_calls is not None and max_calls != budget_guard.limit:
                logger.warning(
                    "LLMClient max_calls=%s ignored; using injected BudgetGuard limit=%s",
                    max_calls,
                    budget_guard.limit,
                )
            self._budget = budget_guard
        else:
            resolved = settings.MAX_LLM_CALLS_PER_SCAN if max_calls is None else max_calls
            if not isinstance(resolved, int) or isinstance(resolved, bool):
                raise ValueError("max_calls must be an int >= 0")
            if resolved < 0:
                raise ValueError("max_calls must be >= 0")
            self._budget = BudgetGuard(limit=resolved)

        self._budget_cap_usd = (
            settings.LLM_BUDGET_CAP_USD if budget_cap_usd is None else budget_cap_usd
        )
        self._instructor_client = instructor_client

    @property
    def budget_guard(self) -> BudgetGuard:
        return self._budget

    @property
    def model(self) -> str:
        return self._model

    @property
    def max_calls(self) -> int:
        return self._budget.limit

    @property
    def calls_made(self) -> int:
        return self._budget.used

    @property
    def remaining_calls(self) -> int:
        return self._budget.remaining

    @property
    def budget_cap_usd(self) -> float:
        return self._budget_cap_usd

    def budget_state(self) -> Mapping[str, int | float | str]:
        """Safe snapshot for logging/metrics (never includes credentials)."""
        snap = self._budget.snapshot()
        return {
            "model": self._model,
            "calls_made": snap["used"],
            "max_calls": snap["limit"],
            "remaining_calls": snap["remaining"],
            "budget_cap_usd": self._budget_cap_usd,
        }

    def __repr__(self) -> str:
        return (
            f"LLMClient(model={self._model!r}, calls_made={self.calls_made}, "
            f"max_calls={self.max_calls})"
        )

    def _secrets(self) -> tuple[str, ...]:
        secrets = [self._api_key]
        if settings.OPENAI_API_KEY:
            secrets.append(settings.OPENAI_API_KEY)
        if settings.ANTHROPIC_API_KEY:
            secrets.append(settings.ANTHROPIC_API_KEY)
        if settings.GEMINI_API_KEY:
            secrets.append(settings.GEMINI_API_KEY)
        if settings.GITHUB_TOKEN:
            secrets.append(settings.GITHUB_TOKEN)
        return tuple(s for s in secrets if s)

    def _build_instructor_client(self) -> Any:
        import instructor
        from litellm import acompletion

        return instructor.from_litellm(acompletion)

    def _get_instructor_client(self) -> Any:
        if self._instructor_client is None:
            self._instructor_client = self._build_instructor_client()
        return self._instructor_client

    async def _reserve_call_slot(self) -> int:
        """Reserve one provider-attempt unit via the shared BudgetGuard."""
        return await self._budget.reserve()

    async def create(
        self,
        response_model: type[T],
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        max_retries: int = 2,
        **kwargs: Any,
    ) -> T:
        """
        Execute a structured completion and validate into ``response_model``.

        Each *actual* provider attempt consumes one budget unit. Instructor
        internal retries are disabled (``max_retries=0`` on the transport);
        this client re-attempts up to ``max_retries`` times, reserving budget
        before every attempt.

        Raises:
            BudgetExhausted / LLMBudgetExceededError: if the next provider
                attempt would exceed the scan budget (no provider call made).
            TypeError: if ``response_model`` is not a Pydantic model class.
            RuntimeError: on provider failures (message sanitized of secrets).
        """
        if not isinstance(response_model, type) or not issubclass(response_model, BaseModel):
            raise TypeError("response_model must be a Pydantic BaseModel subclass")

        if max_retries < 0:
            raise ValueError("max_retries must be >= 0")

        selected_model = model or self._model
        attempts = max_retries + 1
        last_failure: Exception | None = None

        for attempt_index in range(attempts):
            # CRITICAL: reserve BEFORE provider I/O; lock is not held during await.
            call_number = await self._reserve_call_slot()

            logger.info(
                "LLM structured call start call=%s/%s attempt=%s/%s model=%s response_model=%s",
                call_number,
                self.max_calls,
                attempt_index + 1,
                attempts,
                selected_model,
                response_model.__name__,
            )

            create_kwargs: dict[str, Any] = {
                "model": selected_model,
                "messages": messages,
                "response_model": response_model,
                # Disable Instructor/LiteLLM internal retries so each provider
                # attempt is explicitly budget-guarded above.
                "max_retries": 0,
                "max_tokens": kwargs.get("max_tokens", 2500),
                **kwargs,
            }
            # Force max_retries=0 even if kwargs overrode it.
            create_kwargs["max_retries"] = 0
            if self._api_key:
                create_kwargs["api_key"] = self._api_key

            try:
                client = self._get_instructor_client()
                result = await client.chat.completions.create(**create_kwargs)
            except LLMBudgetExceededError:
                raise
            except Exception as exc:
                sanitized = _sanitize_text(str(exc), self._secrets())
                logger.error(
                    "LLM structured call failed call=%s/%s attempt=%s/%s model=%s error=%s",
                    call_number,
                    self.max_calls,
                    attempt_index + 1,
                    attempts,
                    selected_model,
                    sanitized,
                )
                last_failure = RuntimeError(f"LLM structured call failed: {sanitized}")
                last_failure.__cause__ = exc
                if attempt_index + 1 >= attempts:
                    raise last_failure from exc
                # Retry: next loop iteration reserves another budget unit.
                continue

            if not isinstance(result, response_model):
                raise TypeError(f"Expected {response_model.__name__}, got {type(result).__name__}")

            logger.info(
                "LLM structured call ok call=%s/%s attempt=%s/%s model=%s response_model=%s",
                call_number,
                self.max_calls,
                attempt_index + 1,
                attempts,
                selected_model,
                response_model.__name__,
            )
            return result

        # Unreachable if attempts >= 1, but keep mypy satisfied.
        if last_failure is not None:
            raise last_failure
        raise RuntimeError("LLM structured call failed: no attempts executed")
