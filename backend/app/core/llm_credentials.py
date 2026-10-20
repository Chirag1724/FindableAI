"""Provider credential resolution: each provider uses only its own key.

A key is never sent to a provider whose endpoint it cannot authenticate against.
Known key prefixes identify the issuing provider; a key carrying another
provider's prefix (for example an ``xai-`` key placed in ``GROQ_API_KEY``) is
rejected for that provider instead of being tried and burning budget on a
guaranteed 401. Keys without a recognizable prefix are accepted as-is so test
placeholders and future key formats still work.
"""

from __future__ import annotations

import logging

from app.core.config import settings

logger = logging.getLogger(__name__)

# Prefix -> provider that issues keys with that prefix. "xai" has no endpoint in
# this codebase; its keys are therefore unusable everywhere (reported, not tried).
KNOWN_KEY_PREFIXES: dict[str, str] = {
    "gsk_": "groq",
    "AIza": "gemini",
    "AQ.": "gemini",
    "sk-or-": "openrouter",
    "sk-or": "openrouter",
    "nvapi-": "nvidia",
    "sk-ant-": "anthropic",
    "xai-": "xai",
    "sk-": "openai",  # must come after the more specific sk-or- / sk-ant- prefixes
}

SUPPORTED_PROVIDERS: tuple[str, ...] = (
    "groq",
    "gemini",
    "openai",
    "openrouter",
    "nvidia",
    "anthropic",
)


def _parse_provider(model_spec: str) -> str:
    text = (model_spec or "").strip().lower()
    if "/" in text:
        return text.split("/", 1)[0]
    return ""


def key_issuer(key: str | None) -> str | None:
    """Return the provider a key's prefix identifies, or None if unrecognized."""
    k = (key or "").strip()
    if not k:
        return None
    for prefix, provider in KNOWN_KEY_PREFIXES.items():
        if k.startswith(prefix):
            return provider
    return None


def key_matches_provider(provider: str, key: str | None) -> tuple[bool, str]:
    """Return (ok, reason). Rejects keys whose prefix belongs to another provider."""
    p = (provider or "").strip().lower()
    k = (key or "").strip()
    if not k:
        return False, "missing"
    issuer = key_issuer(k)
    if issuer is None or issuer == p:
        return True, "ok"
    return False, f"key_prefix_belongs_to_{issuer}"


def provider_api_keys(provider: str) -> list[str]:
    """Return all configured and valid API keys for a provider."""
    p = (provider or "").strip().lower()
    if p == "groq":
        keys = settings.groq_api_keys_list
        return [k for k in keys if key_matches_provider("groq", k)[0]]
    single = credential_for_provider(p)
    return [single] if single else []


def provider_api_key(provider: str) -> str:
    """Raw configured key for a provider (unvalidated). Never log the return value."""
    p = (provider or "").strip().lower()
    groq_primary = (
        settings.groq_api_keys_list[0] if settings.groq_api_keys_list else settings.GROQ_API_KEY
    )
    mapping = {
        "groq": groq_primary,
        "gemini": settings.GEMINI_API_KEY,
        "openai": settings.OPENAI_API_KEY,
        "openrouter": settings.OPENROUTER_API_KEY,
        "nvidia": settings.NVIDIA_API_KEY,
        "anthropic": settings.ANTHROPIC_API_KEY,
    }
    return (mapping.get(p) or "").strip()


_warned: set[tuple[str, str]] = set()


def credential_for_provider(provider: str, explicit_key: str | None = None) -> str | None:
    """Resolve the key to use for ``provider`` or None if it must be skipped.

    ``explicit_key`` (an ``LLMClient(api_key=...)`` override) is used only when it
    is valid for this provider; otherwise the provider's own configured key is used.
    """
    p = (provider or "").strip().lower()
    if explicit_key:
        ok, _ = key_matches_provider(p, explicit_key)
        if ok:
            return explicit_key.strip()
    configured = provider_api_key(p)
    ok, reason = key_matches_provider(p, configured)
    if ok:
        return configured
    if reason != "missing" and (p, reason) not in _warned:
        _warned.add((p, reason))
        logger.warning(
            "provider_credential_rejected provider=%s reason=%s; provider disabled "
            "(fix the %s_API_KEY value in .env)",
            p,
            reason,
            p.upper(),
        )
    return None


def configured_llm_providers() -> list[str]:
    """Providers with a non-empty key that is valid for that provider."""
    return [name for name in SUPPORTED_PROVIDERS if credential_for_provider(name)]


def provider_credential_report() -> list[dict[str, str]]:
    """Safe (keyless) summary for CLI/readiness output."""
    report: list[dict[str, str]] = []
    for name in SUPPORTED_PROVIDERS:
        raw = provider_api_key(name)
        ok, reason = key_matches_provider(name, raw)
        report.append(
            {
                "provider": name,
                "configured": "yes" if raw else "no",
                "valid_prefix": "yes" if ok else "no",
                "reason": reason,
            }
        )
    return report


def llm_credentials_for_real_scan() -> tuple[bool, str]:
    """Return (ok, public_reason) for a real (non-synthetic) scan."""
    providers = configured_llm_providers()
    if not providers:
        rejected = [
            f"{r['provider'].upper()}_API_KEY ({r['reason']})"
            for r in provider_credential_report()
            if r["configured"] == "yes" and r["valid_prefix"] == "no"
        ]
        hint = f" Rejected: {', '.join(rejected)}." if rejected else ""
        return (
            False,
            "No usable LLM provider credentials configured. Set GROQ_API_KEY, GEMINI_API_KEY, "
            "OPENAI_API_KEY, or OPENROUTER_API_KEY for a real read-only scan "
            "(or set ALLOW_SYNTHETIC_DEMO=true only for explicit demo mode)." + hint,
        )

    heavy = _parse_provider(settings.HEAVY_LLM_MODEL or settings.DEFAULT_LLM_MODEL)
    fast = _parse_provider(settings.FAST_LLM_MODEL or settings.DEFAULT_LLM_MODEL)
    needed = {p for p in (heavy, fast) if p}
    if needed and not any(p in providers for p in needed):
        # Another provider in the failover chain has a key — LLMClient will fail over.
        return True, ""
    return True, ""


__all__ = [
    "KNOWN_KEY_PREFIXES",
    "SUPPORTED_PROVIDERS",
    "configured_llm_providers",
    "credential_for_provider",
    "key_issuer",
    "key_matches_provider",
    "llm_credentials_for_real_scan",
    "provider_api_key",
    "provider_credential_report",
]
