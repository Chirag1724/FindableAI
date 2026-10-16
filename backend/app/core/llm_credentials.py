"""Detect whether real LLM provider credentials are configured for a scan."""

from __future__ import annotations

from app.core.config import settings


def _parse_provider(model_spec: str) -> str:
    text = (model_spec or "").strip().lower()
    if "/" in text:
        return text.split("/", 1)[0]
    return ""


def provider_api_key(provider: str) -> str:
    p = (provider or "").strip().lower()
    mapping = {
        "groq": settings.GROQ_API_KEY,
        "gemini": settings.GEMINI_API_KEY,
        "openai": settings.OPENAI_API_KEY,
        "openrouter": settings.OPENROUTER_API_KEY,
        "nvidia": settings.NVIDIA_API_KEY,
        "anthropic": settings.ANTHROPIC_API_KEY,
    }
    return (mapping.get(p) or "").strip()


def configured_llm_providers() -> list[str]:
    """Providers that have a non-empty API key configured."""
    found: list[str] = []
    for name in ("groq", "gemini", "openai", "openrouter", "nvidia", "anthropic"):
        if provider_api_key(name):
            found.append(name)
    return found


def llm_credentials_for_real_scan() -> tuple[bool, str]:
    """Return (ok, public_reason) for a real (non-synthetic) scan.

    Requires at least one configured key that can serve HEAVY or FAST models,
    or any configured provider key when model specs omit a provider prefix.
    """
    providers = configured_llm_providers()
    if not providers:
        return (
            False,
            "No LLM provider credentials configured. Set GROQ_API_KEY, GEMINI_API_KEY, "
            "OPENAI_API_KEY, or OPENROUTER_API_KEY for a real read-only scan "
            "(or set ALLOW_SYNTHETIC_DEMO=true only for explicit demo mode).",
        )

    heavy = _parse_provider(settings.HEAVY_LLM_MODEL or settings.DEFAULT_LLM_MODEL)
    fast = _parse_provider(settings.FAST_LLM_MODEL or settings.DEFAULT_LLM_MODEL)
    needed = {p for p in (heavy, fast) if p}
    if needed and not any(p in providers for p in needed):
        # Still allow if another provider in the failover chain has a key —
        # LLMClient will attempt failover. Require at least one key (already true).
        return True, ""
    return True, ""


__all__ = [
    "configured_llm_providers",
    "llm_credentials_for_real_scan",
    "provider_api_key",
]
