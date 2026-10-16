"""Shared async LLM client with Instructor structured outputs and call budget.

Recovery policy lives in ``app.core.llm_errors`` (one classifier, bounded per-class
retries). Every outbound provider request reserves one BudgetGuard unit first, so
retries, splits and failovers are all counted exactly once against the scan budget.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import random
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, ClassVar, TypeVar
from urllib.parse import urlparse

from pydantic import BaseModel

from app.core.budget import BudgetExhausted, BudgetGuard, LLMBudgetExceededError
from app.core.config import settings
from app.core.llm_credentials import credential_for_provider
from app.core.llm_errors import (
    Action,
    ClassifiedError,
    ErrorClass,
    LLMAuthError,
    LLMProviderError,
    classify_provider_error,
)
from app.core.provider_throttle import PROVIDER_THROTTLES, estimate_request_tokens

logger = logging.getLogger(__name__)

# Process-wide concurrency gate for structured completion calls.
_global_llm_sema: asyncio.Semaphore | None = None

# Longest provider-advised wait we honor before treating a 429 as exhausted.
RATE_LIMIT_MAX_WAIT_SECONDS = 65.0
BACKOFF_CAP_SECONDS = 60.0

# How long a provider stays tripped (skipped in the chain) per error class.
_TRIP_SECONDS: dict[ErrorClass, float] = {
    ErrorClass.AUTH: 900.0,
    ErrorClass.NOT_FOUND: 900.0,
    ErrorClass.CREDIT: 3600.0,
    ErrorClass.DAILY_QUOTA: 6 * 3600.0,
    ErrorClass.RATE_LIMIT: 60.0,
    ErrorClass.TIMEOUT: 120.0,
    ErrorClass.SERVER: 120.0,
    ErrorClass.CONTEXT_LENGTH: 0.0,
    ErrorClass.INVALID_OUTPUT: 0.0,
    ErrorClass.UNKNOWN: 120.0,
}


def _get_global_llm_semaphore() -> asyncio.Semaphore:
    global _global_llm_sema
    if _global_llm_sema is None:
        _global_llm_sema = asyncio.Semaphore(max(1, int(settings.LLM_GLOBAL_CONCURRENCY)))
    return _global_llm_sema


def _backoff_seconds(base: float, retries_so_far: int, retry_after: float | None) -> float:
    """Exponential backoff with jitter; honors a provider-advised Retry-After."""
    if retry_after is not None and retry_after > 0:
        delay = retry_after + 0.5
    else:
        delay = max(0.5, base) * (2**retries_so_far)
    delay += random.uniform(0.0, min(2.0, delay * 0.25))
    return min(BACKOFF_CAP_SECONDS, delay)


T = TypeVar("T", bound=BaseModel)

_REDACTED = "***REDACTED***"

# Re-export for existing imports: ``from app.core.llm import BudgetExhausted``.
__all__ = [
    "BudgetExhausted",
    "BudgetGuard",
    "LLMAuthError",
    "LLMBudgetExceededError",
    "LLMClient",
    "LLMProviderError",
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

    @property
    def host(self) -> str:
        if not self.base_url:
            return "api.openai.com"
        return urlparse(self.base_url).netloc or self.base_url


_PROVIDER_BASE_URLS: dict[str, str | None] = {
    "groq": "https://api.groq.com/openai/v1",
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai/",
    "openai": None,
    "openrouter": "https://openrouter.ai/api/v1",
    "nvidia": "https://integrate.api.nvidia.com/v1",
}


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
    if s.startswith("nvidia/"):
        return ("nvidia", s)
    if s.startswith("nvidia:"):
        return ("nvidia", s[7:])
    if s.startswith("openai/"):
        sub = s[7:]
        if sub.startswith("gpt-oss"):
            return ("groq", s)
        return ("openai", sub)

    lower = s.lower()
    if lower in ("openrouter", "groq", "gemini", "openai", "nvidia"):
        return (lower, "")

    if "nvidia" in lower or "nemotron" in lower:
        return ("nvidia", s)
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

    Engines must use this class instead of constructing provider clients directly.
    Models remain replaceable via ``DEFAULT_LLM_MODEL`` (e.g. ``groq/…``, ``openai/…``).

    Call accounting is delegated to a scan-scoped ``BudgetGuard``. Multiple
    ``LLMClient`` instances may share one guard so the hard cap is global
    per scan, not per client instance.
    """

    # Circuit breaker: provider -> skipped until expiry (monotonic seconds).
    _global_tripped_providers: ClassVar[set[str]] = set()
    _global_trip_expiry: ClassVar[dict[str, float]] = {}

    @classmethod
    def reset_tripped_providers(cls) -> None:
        """Reset the process-level circuit breaker."""
        cls._global_tripped_providers.clear()
        cls._global_trip_expiry.clear()

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

    # ------------------------------------------------------------------ props
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
        for value in (
            settings.NVIDIA_API_KEY,
            settings.OPENROUTER_API_KEY,
            settings.OPENAI_API_KEY,
            settings.ANTHROPIC_API_KEY,
            settings.GEMINI_API_KEY,
            settings.GROQ_API_KEY,
            settings.GITHUB_TOKEN,
        ):
            if value:
                secrets.append(value)
        return tuple(s for s in secrets if s)

    # --------------------------------------------------------- circuit breaker
    def _is_tripped(self, provider: str) -> bool:
        if provider not in self._tripped_providers:
            return False
        expiry = self._global_trip_expiry.get(provider)
        if expiry is not None and time.monotonic() >= expiry:
            self._tripped_providers.discard(provider)
            self._global_trip_expiry.pop(provider, None)
            return False
        return True

    def _trip(self, provider: str, error_class: ErrorClass, retry_after: float | None) -> None:
        seconds = _TRIP_SECONDS.get(error_class, 120.0)
        if error_class is ErrorClass.RATE_LIMIT and retry_after:
            seconds = max(seconds, float(retry_after))
        if seconds <= 0:
            return
        self._tripped_providers.add(provider)
        self._global_trip_expiry[provider] = time.monotonic() + seconds

    # ---------------------------------------------------------- provider chain
    def _create_endpoint_for_provider(
        self,
        provider_name: str,
        preferred_model: str | None = None,
    ) -> ProviderEndpoint | None:
        import instructor

        if provider_name not in _PROVIDER_BASE_URLS:
            return None
        key = credential_for_provider(provider_name, self._api_key)
        if not key:
            return None

        default_models = {
            "groq": settings.GROQ_MODEL,
            "gemini": settings.GEMINI_MODEL,
            "openai": settings.OPENAI_MODEL,
            "openrouter": settings.OPENROUTER_MODEL,
            "nvidia": settings.NVIDIA_MODEL or "nvidia/nemotron-3.5-lightning-30b-a3b",
        }
        model = preferred_model or default_models[provider_name]
        mode = instructor.Mode.TOOLS if provider_name == "openai" else instructor.Mode.JSON
        return ProviderEndpoint(
            name=provider_name,
            model=model,
            api_key=key,
            base_url=_PROVIDER_BASE_URLS[provider_name],
            mode=mode,
        )

    def _get_provider_chain(self, requested_model: str | None = None) -> list[ProviderEndpoint]:
        # 1. Primary model & provider (defaults to settings.DEFAULT_LLM_MODEL)
        primary_spec = requested_model or self._model or settings.DEFAULT_LLM_MODEL
        p_provider, p_model = _parse_model_spec(primary_spec)

        # 2. Fallback model & provider (defaults to settings.FALLBACK_LLM_MODEL)
        fallback_spec = settings.FALLBACK_LLM_MODEL
        f_provider, f_model = _parse_model_spec(fallback_spec) if fallback_spec else ("", "")

        # 3. Priority: primary -> fallback -> remaining configured providers
        providers_order: list[str] = []
        if p_provider:
            providers_order.append(p_provider)
        if f_provider and f_provider not in providers_order:
            providers_order.append(f_provider)
        for p in ("groq", "openrouter", "gemini", "openai", "nvidia"):
            if p not in providers_order:
                providers_order.append(p)

        # 4. Endpoints — each with ONLY its own credential (or skipped)
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

        # 5. Healthy providers first, tripped ones last (never dropped entirely)
        healthy = [ep for ep in endpoints if not self._is_tripped(ep.name)]
        tripped = [ep for ep in endpoints if self._is_tripped(ep.name)]
        chain = healthy + tripped

        if not chain:
            raise RuntimeError(
                "Either OPENROUTER_API_KEY, GROQ_API_KEY, or GEMINI_API_KEY is required "
                "(a key with another provider's prefix is rejected for that provider)."
            )
        return chain

    def _get_provider_client(self, endpoint: ProviderEndpoint) -> Any:
        if endpoint.name not in self._provider_clients:
            import instructor
            from openai import AsyncOpenAI

            timeout = float(settings.LLM_REQUEST_TIMEOUT_SECONDS)
            connect = float(settings.LLM_CONNECT_TIMEOUT_SECONDS)
            http_timeout: Any = timeout
            try:
                import httpx

                http_timeout = httpx.Timeout(timeout, connect=connect)
            except Exception:
                http_timeout = timeout

            client_kwargs: dict[str, Any] = {
                "api_key": endpoint.api_key,
                "timeout": http_timeout,
                "max_retries": 0,  # Retries owned by LLMClient (avoid nested loops).
            }
            if endpoint.base_url:
                client_kwargs["base_url"] = endpoint.base_url
            raw_client = AsyncOpenAI(**client_kwargs)
            self._provider_clients[endpoint.name] = instructor.from_openai(
                raw_client, mode=endpoint.mode
            )
        return self._provider_clients[endpoint.name]

    # -------------------------------------------------------------- accounting
    async def _reserve_call_slot(self) -> int:
        """Reserve one provider-attempt unit via the shared BudgetGuard."""
        return await self._budget.reserve()

    async def _record_provider_success(
        self, *, tokens_in: int | None = None, tokens_out: int | None = None
    ) -> None:
        try:
            await self._budget.observability.record_provider_success(
                tokens_in=tokens_in, tokens_out=tokens_out
            )
        except Exception:
            logger.debug("provider_success_counter_failed", exc_info=True)

    async def _record_provider_failure(self) -> None:
        try:
            await self._budget.observability.record_provider_failure()
        except Exception:
            logger.debug("provider_failure_counter_failed", exc_info=True)

    async def _record_retry(self) -> None:
        try:
            await self._budget.observability.record_retry()
        except Exception:
            logger.debug("retry_counter_failed", exc_info=True)

    async def _record_failover(self) -> None:
        try:
            await self._budget.observability.record_failover()
            await self._budget.observability.mark_fallback_used()
        except Exception:
            logger.debug("failover_counter_failed", exc_info=True)

    async def _record_duplicate_joined(self) -> None:
        try:
            await self._budget.observability.record_duplicate_joined()
        except Exception:
            logger.debug("duplicate_joined_counter_failed", exc_info=True)

    # -------------------------------------------------------------- public API
    @staticmethod
    def _inflight_key(model: str, response_model: type[BaseModel], messages: Any) -> str:
        raw = json.dumps(
            {"m": model, "r": response_model.__name__, "msgs": messages},
            sort_keys=True,
            default=str,
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

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

        Multi-provider failover uses each provider's own credential. Identical
        in-flight requests on the same scan budget are coalesced into one call.
        """
        if not isinstance(response_model, type) or not issubclass(response_model, BaseModel):
            raise TypeError("response_model must be a Pydantic BaseModel subclass")
        if max_retries < 0:
            raise ValueError("max_retries must be >= 0")

        selected_model = model or self._model
        await self._budget.observability.set_primary_model(selected_model)

        key = self._inflight_key(selected_model, response_model, messages)
        inflight: dict[str, asyncio.Future[Any]] = self._budget.inflight
        async with self._budget._inflight_lock:
            existing = inflight.get(key)
            if existing is not None and not existing.done():
                waiter = True
                fut = existing
            else:
                waiter = False
                fut = asyncio.get_running_loop().create_future()
                inflight[key] = fut

        if waiter:
            logger.info(
                "llm_duplicate_request_joined model=%s response_model=%s",
                selected_model,
                response_model.__name__,
            )
            await self._record_duplicate_joined()
            return await asyncio.shield(fut)

        try:
            result = await self._create_uncoalesced(
                response_model,
                messages,
                selected_model=selected_model,
                max_retries=max_retries,
                **kwargs,
            )
        except asyncio.CancelledError:
            if not fut.done():
                fut.cancel()
            raise
        except BaseException as exc:
            if not fut.done():
                fut.set_exception(exc)
                fut.exception()  # mark retrieved; waiters (if any) re-raise it
            raise
        else:
            if not fut.done():
                fut.set_result(result)
            return result
        finally:
            if inflight.get(key) is fut:
                inflight.pop(key, None)

    async def _create_uncoalesced(
        self,
        response_model: type[T],
        messages: list[dict[str, str]],
        *,
        selected_model: str,
        max_retries: int,
        **kwargs: Any,
    ) -> T:
        configured_cap = max(1, int(settings.LLM_PROVIDER_MAX_ATTEMPTS))
        attempts_cap = min(max_retries + 1, configured_cap)
        sem = _get_global_llm_semaphore()

        if self._instructor_client is not None:
            return await self._create_with_injected_client(
                response_model, messages, selected_model, attempts_cap, sem, **kwargs
            )

        endpoints = self._get_provider_chain(selected_model)
        last_error: LLMProviderError | None = None

        for ep_idx, endpoint in enumerate(endpoints):
            remaining_eps = endpoints[ep_idx + 1 :]
            if self._is_tripped(endpoint.name) and remaining_eps:
                continue
            has_fallback = any(not self._is_tripped(e.name) for e in remaining_eps)
            client = self._get_provider_client(endpoint)
            max_tokens = int(kwargs.get("max_tokens", 4096))
            extra = {k: v for k, v in kwargs.items() if k != "max_tokens"}
            class_retries: dict[ErrorClass, int] = {}
            throttle = PROVIDER_THROTTLES.get(endpoint.name)

            attempt = 0
            while attempt < attempts_cap:
                attempt += 1
                # Budget first: every outbound attempt counts exactly once.
                call_number = await self._reserve_call_slot()
                est_tokens = estimate_request_tokens(messages, max_tokens)
                if throttle is not None:
                    await throttle.acquire(est_tokens)
                logger.info(
                    "llm_request_start call=%s/%s provider=%s model=%s host=%s attempt=%s/%s "
                    "response_model=%s max_tokens=%s est_tokens=%s",
                    call_number,
                    self.max_calls,
                    endpoint.name,
                    endpoint.model,
                    endpoint.host,
                    attempt,
                    attempts_cap,
                    response_model.__name__,
                    max_tokens,
                    est_tokens,
                )
                started = time.perf_counter()
                try:
                    async with sem:
                        result, usage = await asyncio.wait_for(
                            self._invoke(
                                client, endpoint, response_model, messages, max_tokens, extra
                            ),
                            timeout=float(settings.LLM_REQUEST_TIMEOUT_SECONDS),
                        )
                except LLMBudgetExceededError:
                    raise
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    latency_ms = round((time.perf_counter() - started) * 1000, 1)
                    await self._record_provider_failure()
                    sanitized = _sanitize_text(str(exc), self._secrets())
                    ce = classify_provider_error(exc, sanitized)
                    logger.error(
                        "llm_request_failed call=%s/%s provider=%s model=%s class=%s status=%s "
                        "attempt=%s/%s latency_ms=%s error=%s",
                        call_number,
                        self.max_calls,
                        endpoint.name,
                        endpoint.model,
                        ce.error_class.value,
                        ce.status_code,
                        attempt,
                        attempts_cap,
                        latency_ms,
                        sanitized[:300],
                    )
                    last_error = self._typed_error(endpoint, ce, sanitized, attempt)
                    last_error.__cause__ = exc

                    policy = ce.policy
                    used = class_retries.get(ce.error_class, 0)
                    can_retry = used < policy.max_retries and attempt < attempts_cap
                    if (
                        ce.error_class is ErrorClass.RATE_LIMIT
                        and ce.retry_after is not None
                        and ce.retry_after > RATE_LIMIT_MAX_WAIT_SECONDS
                    ):
                        can_retry = False
                    if can_retry:
                        class_retries[ce.error_class] = used + 1
                        delay = _backoff_seconds(policy.base_backoff, used, ce.retry_after)
                        await self._record_retry()
                        logger.warning(
                            "llm_retry provider=%s model=%s class=%s retry=%s/%s wait=%.1fs",
                            endpoint.name,
                            endpoint.model,
                            ce.error_class.value,
                            used + 1,
                            policy.max_retries,
                            delay,
                        )
                        await asyncio.sleep(delay)
                        continue

                    action = policy.on_exhausted
                    if action is Action.FAILOVER and has_fallback:
                        self._trip(endpoint.name, ce.error_class, ce.retry_after)
                        await self._record_failover()
                        next_ep = next(e for e in remaining_eps if not self._is_tripped(e.name))
                        logger.warning(
                            "llm_failover from=%s to=%s class=%s (own credentials each)",
                            endpoint.name,
                            next_ep.name,
                            ce.error_class.value,
                        )
                        break
                    if action in (Action.FAILOVER, Action.STOP) and _TRIP_SECONDS.get(
                        ce.error_class, 0
                    ):
                        # No fallback: remember the outage so sibling requests skip quickly.
                        self._trip(endpoint.name, ce.error_class, ce.retry_after)
                    raise last_error from exc

                # ---- success
                latency_ms = round((time.perf_counter() - started) * 1000, 1)
                if not isinstance(result, response_model):
                    await self._record_provider_failure()
                    raise TypeError(
                        f"Expected {response_model.__name__}, got {type(result).__name__}"
                    )
                tokens_in, tokens_out = usage if usage else (None, None)
                if ep_idx > 0:
                    await self._budget.observability.mark_fallback_used()
                await self._record_provider_success(tokens_in=tokens_in, tokens_out=tokens_out)
                if throttle is not None and tokens_in is not None and tokens_out is not None:
                    throttle.record_actual(int(tokens_in) + int(tokens_out))
                logger.info(
                    "llm_request_ok call=%s/%s provider=%s model=%s host=%s response_model=%s "
                    "latency_ms=%s tokens_in=%s tokens_out=%s",
                    call_number,
                    self.max_calls,
                    endpoint.name,
                    endpoint.model,
                    endpoint.host,
                    response_model.__name__,
                    latency_ms,
                    tokens_in,
                    tokens_out,
                )
                return result

        if last_error is not None:
            raise last_error
        raise RuntimeError("LLM structured call failed: no provider succeeded")

    @staticmethod
    def _typed_error(
        endpoint: ProviderEndpoint, ce: ClassifiedError, sanitized: str, attempts: int
    ) -> LLMProviderError:
        message = f"LLM structured call failed ({endpoint.name}/{endpoint.model}, {ce.error_class.value}): {sanitized}"
        if ce.error_class is ErrorClass.AUTH:
            return LLMAuthError(
                message,
                provider=endpoint.name,
                model=endpoint.model,
                error_class=ce.error_class,
                attempts=attempts,
            )
        return LLMProviderError(
            message,
            provider=endpoint.name,
            model=endpoint.model,
            error_class=ce.error_class,
            attempts=attempts,
        )

    async def _invoke(
        self,
        client: Any,
        endpoint: ProviderEndpoint,
        response_model: type[T],
        messages: list[dict[str, str]],
        max_tokens: int,
        extra: dict[str, Any],
    ) -> tuple[Any, tuple[int, int] | None]:
        create_kwargs: dict[str, Any] = {
            "model": endpoint.model,
            "messages": messages,
            "response_model": response_model,
            "max_retries": 0,  # instructor's own retry loop disabled; ours is bounded
            "max_tokens": max_tokens,
            **extra,
        }
        create_kwargs["max_retries"] = 0
        with_completion = getattr(client.chat.completions, "create_with_completion", None)
        if with_completion is not None:
            result, completion = await with_completion(**create_kwargs)
            usage = getattr(completion, "usage", None)
            if usage is not None:
                p = getattr(usage, "prompt_tokens", None)
                c = getattr(usage, "completion_tokens", None)
                if isinstance(p, int) and isinstance(c, int):
                    return result, (p, c)
            return result, None
        result = await client.chat.completions.create(**create_kwargs)
        return result, None

    async def _create_with_injected_client(
        self,
        response_model: type[T],
        messages: list[dict[str, str]],
        selected_model: str,
        attempts_cap: int,
        sem: asyncio.Semaphore,
        **kwargs: Any,
    ) -> T:
        """Test/injection path: one logical provider, bounded retries, no failover."""
        for attempt_index in range(attempts_cap):
            call_number = await self._reserve_call_slot()
            logger.info(
                "llm_request_start call=%s/%s provider=injected model=%s attempt=%s/%s response_model=%s",
                call_number,
                self.max_calls,
                selected_model,
                attempt_index + 1,
                attempts_cap,
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
                async with sem:
                    result = await asyncio.wait_for(
                        self._instructor_client.chat.completions.create(**create_kwargs),
                        timeout=float(settings.LLM_REQUEST_TIMEOUT_SECONDS),
                    )
            except LLMBudgetExceededError:
                raise
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                await self._record_provider_failure()
                sanitized = _sanitize_text(str(exc), self._secrets())
                ce = classify_provider_error(exc, sanitized)
                logger.error(
                    "llm_request_failed call=%s/%s provider=injected model=%s class=%s attempt=%s/%s error=%s",
                    call_number,
                    self.max_calls,
                    selected_model,
                    ce.error_class.value,
                    attempt_index + 1,
                    attempts_cap,
                    sanitized[:300],
                )
                endpoint = ProviderEndpoint(
                    name="injected", model=selected_model, api_key="", base_url=None, mode=None
                )
                typed = self._typed_error(endpoint, ce, sanitized, attempt_index + 1)
                typed.__cause__ = exc
                if ce.permanent or attempt_index + 1 >= attempts_cap:
                    raise typed from exc
                await self._record_retry()
                await asyncio.sleep(_backoff_seconds(0.5, attempt_index, None) * 0.1)
                continue

            if not isinstance(result, response_model):
                await self._record_provider_failure()
                raise TypeError(f"Expected {response_model.__name__}, got {type(result).__name__}")
            await self._record_provider_success()
            return result
        raise RuntimeError("LLM structured call failed: no attempts available")
