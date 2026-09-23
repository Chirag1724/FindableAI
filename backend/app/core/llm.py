"""Shared async LLM client with Instructor structured outputs and call budget."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping, Sequence
from typing import Any, TypeVar

from pydantic import BaseModel

from app.core.config import settings

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

_REDACTED = "***REDACTED***"


class BudgetExhausted(Exception):
    """Raised when the per-pipeline LLM call budget has been fully consumed."""

    def __init__(self, calls_made: int, max_calls: int) -> None:
        self.calls_made = calls_made
        self.max_calls = max_calls
        super().__init__(
            f"LLM budget exhausted: {calls_made}/{max_calls} calls used (limit={max_calls})"
        )


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
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        max_calls: int | None = None,
        budget_cap_usd: float | None = None,
        instructor_client: Any | None = None,
    ) -> None:
        self._api_key = settings.GROQ_API_KEY if api_key is None else api_key
        self._model = model or settings.DEFAULT_LLM_MODEL
        self._max_calls = settings.MAX_LLM_CALLS_PER_SCAN if max_calls is None else max_calls
        if self._max_calls < 1:
            raise ValueError("max_calls must be >= 1")

        self._budget_cap_usd = (
            settings.LLM_BUDGET_CAP_USD if budget_cap_usd is None else budget_cap_usd
        )
        self._calls_made = 0
        self._lock = asyncio.Lock()
        self._instructor_client = instructor_client

    @property
    def model(self) -> str:
        return self._model

    @property
    def max_calls(self) -> int:
        return self._max_calls

    @property
    def calls_made(self) -> int:
        return self._calls_made

    @property
    def remaining_calls(self) -> int:
        return max(0, self._max_calls - self._calls_made)

    @property
    def budget_cap_usd(self) -> float:
        return self._budget_cap_usd

    def budget_state(self) -> Mapping[str, int | float | str]:
        """Safe snapshot for logging/metrics (never includes credentials)."""
        return {
            "model": self._model,
            "calls_made": self._calls_made,
            "max_calls": self._max_calls,
            "remaining_calls": self.remaining_calls,
            "budget_cap_usd": self._budget_cap_usd,
        }

    def __repr__(self) -> str:
        return (
            f"LLMClient(model={self._model!r}, calls_made={self._calls_made}, "
            f"max_calls={self._max_calls})"
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
        async with self._lock:
            if self._calls_made >= self._max_calls:
                raise BudgetExhausted(self._calls_made, self._max_calls)
            self._calls_made += 1
            return self._calls_made

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

        Raises:
            BudgetExhausted: if the call would exceed ``max_calls``.
            TypeError: if ``response_model`` is not a Pydantic model class.
            RuntimeError: on provider failures (message sanitized of secrets).
        """
        if not isinstance(response_model, type) or not issubclass(response_model, BaseModel):
            raise TypeError("response_model must be a Pydantic BaseModel subclass")

        call_number = await self._reserve_call_slot()
        selected_model = model or self._model

        logger.info(
            "LLM structured call start call=%s/%s model=%s response_model=%s",
            call_number,
            self._max_calls,
            selected_model,
            response_model.__name__,
        )

        create_kwargs: dict[str, Any] = {
            "model": selected_model,
            "messages": messages,
            "response_model": response_model,
            "max_retries": max_retries,
            **kwargs,
        }
        if self._api_key:
            create_kwargs["api_key"] = self._api_key

        try:
            client = self._get_instructor_client()
            result = await client.chat.completions.create(**create_kwargs)
        except BudgetExhausted:
            raise
        except Exception as exc:
            sanitized = _sanitize_text(str(exc), self._secrets())
            logger.error(
                "LLM structured call failed call=%s/%s model=%s error=%s",
                call_number,
                self._max_calls,
                selected_model,
                sanitized,
            )
            raise RuntimeError(f"LLM structured call failed: {sanitized}") from exc

        if not isinstance(result, response_model):
            raise TypeError(f"Expected {response_model.__name__}, got {type(result).__name__}")

        logger.info(
            "LLM structured call ok call=%s/%s model=%s response_model=%s",
            call_number,
            self._max_calls,
            selected_model,
            response_model.__name__,
        )
        return result
