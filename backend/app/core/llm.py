"""Shared async LLM client with Instructor structured outputs and call budget."""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, ClassVar, TypeVar

from pydantic import BaseModel

from app.core.budget import BudgetExhausted, BudgetGuard, LLMBudgetExceededError
from app.core.config import settings

logger = logging.getLogger(__name__)

_RETRY_AFTER_RE = re.compile(r"try again in (?:(\d+)m)?([\d\.]+)s", re.IGNORECASE)


def _parse_retry_after(text: str) -> float | None:
    match = _RETRY_AFTER_RE.search(text)
    if not match:
        return None
    mins = float(match.group(1)) if match.group(1) else 0.0
    secs = float(match.group(2)) if match.group(2) else 0.0
    return mins * 60.0 + secs


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


@dataclass(frozen=True, slots=True)
class ProviderEndpoint:
    name: str
    model: str
    api_key: str
    base_url: str | None
    mode: Any


def _parse_model_spec(spec: str) -> tuple[str, str]:
    """Parse a model identifier or prefix into (provider_name, clean_model_name).

    Examples:
        'groq/openai/gpt-oss-120b' -> ('groq', 'openai/gpt-oss-120b')
        'gemini/gemini-3.6-flash'  -> ('gemini', 'gemini-3.6-flash')
        'openai/gpt-4o-mini'       -> ('openai', 'gpt-4o-mini')
        'gemini-3.6-flash'         -> ('gemini', 'gemini-3.6-flash')
        'gpt-4o-mini'              -> ('openai', 'gpt-4o-mini')
    """
    s = (spec or "").strip()
    if not s:
        return ("", "")

    if s.startswith("openrouter/"):
        return ("openrouter", s[11:])
    if s.startswith("groq/"):
        return ("groq", s[5:])
    if s.startswith("gemini/"):
        return ("gemini", s[7:])
    if s.startswith("openai/"):
        sub = s[7:]
        if sub.startswith("gpt-oss"):
            return ("groq", s)
        return ("openai", sub)

    lower = s.lower()
    if lower in ("openrouter", "groq", "gemini", "openai"):
        return (lower, "")

    if "openrouter" in lower:
        return ("openrouter", s.split("/", 1)[-1] if "/" in s else "")
    if "gemini" in lower:
        return ("gemini", s.split("/")[-1])
    if any(k in lower for k in ("gpt-oss", "qwen", "llama", "mixtral", "gemma")):
        return ("groq", s)
    if any(k in lower for k in ("gpt-4", "gpt-3.5", "o1", "o3", "o4")):
        return ("openai", s.split("/")[-1])

    return ("groq", s)


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

    _global_tripped_providers: ClassVar[set[str]] = set()
    _global_daily_exhausted_providers: ClassVar[set[str]] = set()
    _openrouter_max_tokens_override: ClassVar[int | None] = None

    @classmethod
    def reset_tripped_providers(cls) -> None:
        """Reset the process-level circuit breaker and daily exhaustion tracker."""
        cls._global_tripped_providers.clear()
        cls._global_daily_exhausted_providers.clear()

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
        self._provider_clients: dict[str, Any] = {}
        self._tripped_providers: set[str] = self._global_tripped_providers

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
        if settings.OPENROUTER_API_KEY:
            secrets.append(settings.OPENROUTER_API_KEY)
        if settings.OPENAI_API_KEY:
            secrets.append(settings.OPENAI_API_KEY)
        if settings.ANTHROPIC_API_KEY:
            secrets.append(settings.ANTHROPIC_API_KEY)
        if settings.GEMINI_API_KEY:
            secrets.append(settings.GEMINI_API_KEY)
        if settings.GITHUB_TOKEN:
            secrets.append(settings.GITHUB_TOKEN)
        return tuple(s for s in secrets if s)

    def _create_endpoint_for_provider(
        self,
        provider_name: str,
        preferred_model: str | None = None,
    ) -> ProviderEndpoint | None:
        import instructor

        if provider_name == "openrouter":
            openrouter_key = (
                self._api_key
                if (self._api_key and self._api_key.startswith("sk-or-"))
                else settings.OPENROUTER_API_KEY
            )
            if not openrouter_key and self._api_key and self._api_key.startswith("sk-or"):
                openrouter_key = self._api_key
            if not openrouter_key:
                return None

            model = preferred_model or settings.OPENROUTER_MODEL
            return ProviderEndpoint(
                name="openrouter",
                model=model,
                api_key=openrouter_key,
                base_url="https://openrouter.ai/api/v1",
                mode=instructor.Mode.JSON,
            )

        if provider_name == "groq":
            groq_key = (
                self._api_key
                if (self._api_key and self._api_key.startswith("gsk_"))
                else settings.GROQ_API_KEY
            )
            if (
                not groq_key
                and self._api_key
                and not any(self._api_key.startswith(p) for p in ("AIza", "AQ.", "sk-"))
            ):
                groq_key = self._api_key
            if not groq_key:
                return None

            model = preferred_model or settings.GROQ_MODEL
            return ProviderEndpoint(
                name="groq",
                model=model,
                api_key=groq_key,
                base_url="https://api.groq.com/openai/v1",
                mode=instructor.Mode.JSON,
            )

        if provider_name == "gemini":
            gemini_key = (
                self._api_key
                if (
                    self._api_key
                    and (self._api_key.startswith("AIza") or self._api_key.startswith("AQ."))
                )
                else settings.GEMINI_API_KEY
            )
            if (
                not gemini_key
                and self._api_key
                and not any(self._api_key.startswith(p) for p in ("gsk_", "sk-"))
            ):
                gemini_key = self._api_key
            if not gemini_key:
                return None

            model = preferred_model or settings.GEMINI_MODEL
            return ProviderEndpoint(
                name="gemini",
                model=model,
                api_key=gemini_key,
                base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
                mode=instructor.Mode.JSON,
            )

        if provider_name == "openai":
            openai_key = (
                self._api_key
                if (
                    self._api_key
                    and self._api_key.startswith("sk-")
                    and not self._api_key.startswith("gsk_")
                    and not self._api_key.startswith("sk-or")
                )
                else settings.OPENAI_API_KEY
            )
            if (
                not openai_key
                and self._api_key
                and not any(self._api_key.startswith(p) for p in ("gsk_", "AIza", "AQ.", "sk-or"))
            ):
                openai_key = self._api_key
            if not openai_key:
                return None

            model = preferred_model or settings.OPENAI_MODEL
            return ProviderEndpoint(
                name="openai",
                model=model,
                api_key=openai_key,
                base_url=None,
                mode=instructor.Mode.TOOLS,
            )

        return None

    def _get_provider_chain(self, requested_model: str | None = None) -> list[ProviderEndpoint]:
        # 1. Determine primary model & provider (defaults to settings.DEFAULT_LLM_MODEL)
        primary_spec = requested_model or self._model or settings.DEFAULT_LLM_MODEL
        p_provider, p_model = _parse_model_spec(primary_spec)

        # 2. Determine fallback model & provider (defaults to settings.FALLBACK_LLM_MODEL)
        fallback_spec = settings.FALLBACK_LLM_MODEL
        f_provider, f_model = _parse_model_spec(fallback_spec) if fallback_spec else ("", "")

        # 3. Dynamic provider priority ordering: primary -> fallback -> remaining providers
        providers_order: list[str] = []
        if p_provider:
            providers_order.append(p_provider)
        if f_provider and f_provider not in providers_order:
            providers_order.append(f_provider)
        for p in ("openrouter", "groq", "gemini", "openai"):
            if p not in providers_order:
                providers_order.append(p)

        # 4. Instantiate endpoints with explicit or configured default models
        endpoints: list[ProviderEndpoint] = []
        for p in providers_order:
            preferred = None
            if p == p_provider and p_model:
                preferred = p_model
            elif p == f_provider and f_model:
                preferred = f_model

            ep = self._create_endpoint_for_provider(p, preferred_model=preferred)
            if ep is not None:
                endpoints.append(ep)

        # 5. Filter out providers known to have daily quotas exhausted across the process
        available = [
            ep for ep in endpoints if ep.name not in self._global_daily_exhausted_providers
        ]
        endpoints_to_use = available if available else endpoints

        # 6. Order healthy providers first, followed by tripped providers (circuit breaker)
        healthy = [ep for ep in endpoints_to_use if ep.name not in self._tripped_providers]
        tripped = [ep for ep in endpoints_to_use if ep.name in self._tripped_providers]
        chain = healthy + tripped

        if not chain:
            raise RuntimeError(
                "Either OPENROUTER_API_KEY, GROQ_API_KEY, or GEMINI_API_KEY is required."
            )

        return chain

    def _get_provider_client(self, endpoint: ProviderEndpoint) -> Any:
        if endpoint.name not in self._provider_clients:
            import instructor
            from openai import AsyncOpenAI

            raw_client = (
                AsyncOpenAI(api_key=endpoint.api_key, base_url=endpoint.base_url)
                if endpoint.base_url
                else AsyncOpenAI(api_key=endpoint.api_key)
            )
            self._provider_clients[endpoint.name] = instructor.from_openai(
                raw_client, mode=endpoint.mode
            )
        return self._provider_clients[endpoint.name]

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

        Supports automatic multi-provider fallback (Groq -> Gemini -> OpenAI)
        with shared scan-scoped budget guard accounting.
        """
        if not isinstance(response_model, type) or not issubclass(response_model, BaseModel):
            raise TypeError("response_model must be a Pydantic BaseModel subclass")

        if max_retries < 0:
            raise ValueError("max_retries must be >= 0")

        selected_model = model or self._model
        attempts = max_retries + 1
        last_failure: Exception | None = None

        if self._instructor_client is not None:
            for attempt_index in range(attempts):
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
                    "messages": messages,
                    "response_model": response_model,
                    "max_retries": 0,
                    "max_tokens": kwargs.get("max_tokens", 8192),
                    "model": selected_model,
                    **kwargs,
                }
                create_kwargs["max_retries"] = 0
                if self._api_key:
                    create_kwargs["api_key"] = self._api_key

                try:
                    result = await self._instructor_client.chat.completions.create(**create_kwargs)
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
                    continue

                if not isinstance(result, response_model):
                    raise TypeError(
                        f"Expected {response_model.__name__}, got {type(result).__name__}"
                    )
                return result

        endpoints = self._get_provider_chain(selected_model)
        for ep_idx, endpoint in enumerate(endpoints):
            # Dynamic circuit-breaker check: if this provider was tripped by an earlier/concurrent call,
            # skip it immediately to avoid wasted attempts or duplicate 429 errors.
            if endpoint.name in self._tripped_providers and ep_idx + 1 < len(endpoints):
                continue

            client = self._get_provider_client(endpoint)
            provider_attempts = max(attempts, 4)
            has_fallback = ep_idx + 1 < len(endpoints)

            # Safe completion ceiling calculated per provider without corrupting kwargs for failover providers
            requested_max_tokens = kwargs.get("max_tokens", 4096)
            if endpoint.name == "openrouter":
                safe_limit = getattr(LLMClient, "_openrouter_max_tokens_override", 1000) or 1000
                provider_max_tokens = min(requested_max_tokens, safe_limit)
            elif endpoint.name == "groq":
                provider_max_tokens = max(requested_max_tokens, 2048)
            else:
                provider_max_tokens = requested_max_tokens

            for attempt_index in range(provider_attempts):
                call_number = await self._reserve_call_slot()
                logger.info(
                    "LLM structured call start call=%s/%s provider=%s model=%s response_model=%s max_tokens=%d",
                    call_number,
                    self.max_calls,
                    endpoint.name,
                    endpoint.model,
                    response_model.__name__,
                    provider_max_tokens,
                )

                create_kwargs = {
                    "model": endpoint.model,
                    "messages": messages,
                    "response_model": response_model,
                    "max_retries": 0,
                    "max_tokens": provider_max_tokens,
                    **{k: v for k, v in kwargs.items() if k != "max_tokens"},
                }
                create_kwargs["max_retries"] = 0

                try:
                    result = await client.chat.completions.create(**create_kwargs)
                except LLMBudgetExceededError:
                    raise
                except Exception as exc:
                    sanitized = _sanitize_text(str(exc), self._secrets())
                    logger.error(
                        "LLM call failed call=%s/%s provider=%s model=%s error=%s",
                        call_number,
                        self.max_calls,
                        endpoint.name,
                        endpoint.model,
                        sanitized,
                    )
                    last_failure = RuntimeError(
                        f"LLM structured call failed ({endpoint.name}): {sanitized}"
                    )
                    last_failure.__cause__ = exc

                    is_credit_limit = (
                        "can only afford" in sanitized.lower()
                        or "requires more credits" in sanitized.lower()
                        or "lower max_tokens" in sanitized.lower()
                        or "fewer max_tokens" in sanitized.lower()
                        or "in_flight" in sanitized.lower()
                        or "in-flight" in sanitized.lower()
                        or "402" in sanitized
                    )
                    if is_credit_limit:
                        match = re.search(r"can only afford (\d+)", sanitized, re.IGNORECASE)
                        if match:
                            affordable = int(match.group(1))
                            if affordable < 200:
                                self._global_daily_exhausted_providers.add(endpoint.name)
                                self._tripped_providers.add(endpoint.name)
                                if has_fallback:
                                    next_ep = endpoints[ep_idx + 1]
                                    logger.warning(
                                        "Provider '%s' has insufficient token balance (%d); failing over to '%s'",
                                        endpoint.name,
                                        affordable,
                                        next_ep.name,
                                    )
                                    break
                            LLMClient._openrouter_max_tokens_override = max(200, affordable - 30)
                            provider_max_tokens = LLMClient._openrouter_max_tokens_override
                        else:
                            provider_max_tokens = max(250, provider_max_tokens // 2)

                        if attempt_index + 1 < provider_attempts:
                            sleep_delay = (
                                3.0
                                if (
                                    "in-flight" in sanitized.lower()
                                    or "in_flight" in sanitized.lower()
                                )
                                else 0.5
                            )
                            logger.warning(
                                "LLM credit/in-flight ceiling hit on provider=%s; lowering max_tokens to %d and waiting %.1fs before retrying",
                                endpoint.name,
                                provider_max_tokens,
                                sleep_delay,
                            )
                            await asyncio.sleep(sleep_delay)
                            continue

                    is_token_truncation = "max_tokens length limit" in sanitized.lower()
                    if is_token_truncation and attempt_index + 1 < provider_attempts:
                        provider_max_tokens = min(4096, provider_max_tokens + 1024)
                        logger.warning(
                            "LLM output truncated on provider=%s; increasing max_tokens to %d and retrying",
                            endpoint.name,
                            provider_max_tokens,
                        )
                        continue

                    is_rate_limit = "rate limit" in sanitized.lower() or "429" in sanitized
                    is_daily_quota = (
                        "resource_exhausted" in sanitized.lower()
                        or "generaterequestsperday" in sanitized.lower()
                    )
                    has_fallback = ep_idx + 1 < len(endpoints)

                    if is_daily_quota:
                        self._global_daily_exhausted_providers.add(endpoint.name)
                        self._tripped_providers.add(endpoint.name)
                        if has_fallback:
                            next_ep = endpoints[ep_idx + 1]
                            logger.warning(
                                "Provider '%s' exhausted daily quota; tripping circuit breaker and failing over to '%s'",
                                endpoint.name,
                                next_ep.name,
                            )
                            break

                    retry_delay = _parse_retry_after(sanitized)
                    if retry_delay and retry_delay > 30.0 and has_fallback:
                        self._tripped_providers.add(endpoint.name)
                        next_ep = endpoints[ep_idx + 1]
                        logger.warning(
                            "Provider '%s' rate limited with long delay (%.1fs); failing over to '%s'",
                            endpoint.name,
                            retry_delay,
                            next_ep.name,
                        )
                        break

                    if is_rate_limit and attempt_index + 1 < provider_attempts:
                        backoff = min(
                            15.0, (retry_delay + 0.5) if retry_delay else (attempt_index + 1) * 3.0
                        )
                        logger.warning(
                            "LLM rate limited call=%s provider=%s; waiting %.1fs for token bucket reset",
                            call_number,
                            endpoint.name,
                            backoff,
                        )
                        await asyncio.sleep(backoff)
                        continue

                    if attempt_index + 1 < provider_attempts and not is_daily_quota:
                        backoff = 1.0 * (attempt_index + 1)
                        logger.warning(
                            "LLM call attempt %d failed on provider=%s (%s); retrying in %.1fs",
                            attempt_index + 1,
                            endpoint.name,
                            sanitized,
                            backoff,
                        )
                        await asyncio.sleep(backoff)
                        continue

                    if has_fallback:
                        self._tripped_providers.add(endpoint.name)
                        next_ep = endpoints[ep_idx + 1]
                        logger.warning(
                            "Provider '%s' failed (%s) after %d attempts; tripped circuit breaker and failing over to provider '%s' (model=%s) for remaining claims",
                            endpoint.name,
                            sanitized,
                            attempt_index + 1,
                            next_ep.name,
                            next_ep.model,
                        )
                        break

                    if attempt_index + 1 >= provider_attempts:
                        raise last_failure from exc
                    continue

                if not isinstance(result, response_model):
                    raise TypeError(
                        f"Expected {response_model.__name__}, got {type(result).__name__}"
                    )

                logger.info(
                    "LLM structured call ok call=%s/%s provider=%s model=%s response_model=%s",
                    call_number,
                    self.max_calls,
                    endpoint.name,
                    endpoint.model,
                    response_model.__name__,
                )
                return result

        if last_failure is not None:
            raise last_failure
        raise RuntimeError("LLM structured call failed: no provider succeeded")
