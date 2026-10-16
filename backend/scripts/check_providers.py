#!/usr/bin/env python3
"""Verify LLM provider credentials with exactly one minimal request per provider.

Usage (from backend/):
    python scripts/check_providers.py            # all configured providers
    python scripts/check_providers.py --json

Prints provider, model, endpoint host, HTTP status/result and latency. Never
prints keys. Exit codes: 0 all OK, 2 at least one auth failure (401/403 or a key
whose prefix belongs to another provider), 1 other failure / nothing configured.
Does not touch any scan budget.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from typing import Any

from app.core.config import settings
from app.core.llm import LLMClient, ProviderEndpoint, _parse_model_spec
from app.core.llm_credentials import provider_credential_report
from app.core.llm_errors import classify_provider_error


def _endpoints_to_check() -> list[ProviderEndpoint]:
    """One endpoint per (provider, model) the pipeline would actually use."""
    seen: set[tuple[str, str]] = set()
    out: list[ProviderEndpoint] = []
    for spec in (settings.HEAVY_LLM_MODEL, settings.FAST_LLM_MODEL):
        provider, model = _parse_model_spec(spec)
        client = LLMClient(model=spec, max_calls=0)
        ep = client._create_endpoint_for_provider(provider, preferred_model=model or None)
        if ep is None:
            continue
        key = (ep.name, ep.model)
        if key not in seen:
            seen.add(key)
            out.append(ep)
    # Remaining configured providers (fallback chain) with their default model.
    client = LLMClient(max_calls=0)
    for provider in ("groq", "gemini", "openai", "openrouter", "nvidia"):
        ep = client._create_endpoint_for_provider(provider)
        if ep is None or ep.name in {e.name for e in out}:
            continue
        out.append(ep)
    return out


async def _probe(ep: ProviderEndpoint) -> dict[str, Any]:
    from openai import AsyncOpenAI

    kwargs: dict[str, Any] = {"api_key": ep.api_key, "max_retries": 0, "timeout": 30.0}
    if ep.base_url:
        kwargs["base_url"] = ep.base_url
    client = AsyncOpenAI(**kwargs)
    started = time.perf_counter()
    row: dict[str, Any] = {"provider": ep.name, "model": ep.model, "host": ep.host}
    try:
        resp = await client.chat.completions.create(
            model=ep.model,
            messages=[{"role": "user", "content": "Reply with the single word OK."}],
            max_tokens=5,
            temperature=0,
        )
        row["status"] = "ok"
        row["http_status"] = 200
        usage = getattr(resp, "usage", None)
        if usage is not None:
            row["tokens"] = int(getattr(usage, "total_tokens", 0) or 0)
    except Exception as exc:  # classified, never re-raised with the key inside
        sanitized = str(exc).replace(ep.api_key, "***REDACTED***")
        ce = classify_provider_error(exc, sanitized)
        row["status"] = f"error:{ce.error_class.value}"
        row["http_status"] = ce.status_code
        row["detail"] = sanitized[:200]
    finally:
        row["latency_ms"] = round((time.perf_counter() - started) * 1000, 1)
        await client.close()
    return row


async def _main(as_json: bool) -> int:
    report = provider_credential_report()
    rejected = [r for r in report if r["configured"] == "yes" and r["valid_prefix"] == "no"]
    endpoints = _endpoints_to_check()
    rows = [await _probe(ep) for ep in endpoints]

    exit_code = 0
    if rejected:
        exit_code = 2
    if not rows and not rejected:
        exit_code = 1
    for row in rows:
        if row["status"].startswith("error:auth"):
            exit_code = 2
        elif row["status"] != "ok" and exit_code == 0:
            exit_code = 1

    if as_json:
        print(json.dumps({"credentials": report, "probes": rows, "exit_code": exit_code}, indent=2))
        return exit_code

    print("Credential prefixes (no values shown):")
    for r in report:
        if r["configured"] == "yes":
            print(
                f"  {r['provider']:<11} configured  prefix_ok={r['valid_prefix']:<3} {r['reason']}"
            )
    print("Probes (one minimal request each):")
    for row in rows:
        line = (
            f"  {row['provider']:<11} {row['model']:<28} {row['host']:<40} "
            f"{row['status']:<22} http={row.get('http_status')} {row['latency_ms']}ms"
        )
        print(line)
        if row.get("detail"):
            print(f"      {row['detail']}")
    if not rows:
        print("  (no provider endpoints could be built from the configured keys)")
    print(f"exit_code={exit_code}")
    return exit_code


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    return asyncio.run(_main(args.json))


if __name__ == "__main__":
    raise SystemExit(main())
