#!/usr/bin/env python3
"""Submit one read-only scan and poll until terminal state (no GitHub PR).

Usage (from backend/ with API running):
  python scripts/local_smoke_scan.py --url http://127.0.0.1:8080/index.html

Fails clearly when LLM credentials are missing (HTTP 503) or when the job
does not reach a terminal state before --timeout.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

TERMINAL = frozenset({"completed", "failed"})


def _request(
    method: str,
    url: str,
    *,
    body: dict | None = None,
    api_key: str | None = None,
    timeout: float = 30.0,
) -> tuple[int, dict | list | str]:
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if api_key:
        headers["X-API-Key"] = api_key
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            code = int(resp.status)
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        code = int(exc.code)
    try:
        parsed: dict | list | str = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        parsed = raw
    return code, parsed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-url",
        default=os.environ.get("BACKEND_URL", "http://127.0.0.1:8000"),
        help="API base URL",
    )
    parser.add_argument(
        "--url",
        required=True,
        help="Authorized target URL (omit repo_url; smoke never opens a PR)",
    )
    parser.add_argument("--max-pages", type=int, default=2)
    parser.add_argument("--timeout", type=float, default=600.0, help="Seconds to wait")
    parser.add_argument("--poll-interval", type=float, default=2.0)
    parser.add_argument(
        "--api-key",
        default=os.environ.get("API_KEY", ""),
        help="X-API-Key when API_KEY is configured",
    )
    args = parser.parse_args()
    base = args.base_url.rstrip("/")
    api_key = (args.api_key or "").strip() or None

    code, health = _request("GET", f"{base}/api/v1/health", api_key=api_key)
    if code != 200:
        print(f"FAIL: health check HTTP {code}: {health}", file=sys.stderr)
        return 2
    print(f"OK health: {health}")

    # Never send repo_url — smoke is incapable of opening a GitHub PR.
    payload = {"url": args.url, "max_pages": int(args.max_pages)}
    code, created = _request(
        "POST", f"{base}/api/v1/scans", body=payload, api_key=api_key
    )
    if code == 503:
        print(
            "FAIL: scan rejected (missing credentials or durability). "
            f"Detail: {created}",
            file=sys.stderr,
        )
        return 3
    if code != 202 or not isinstance(created, dict) or "scan_id" not in created:
        print(f"FAIL: create_scan HTTP {code}: {created}", file=sys.stderr)
        return 4

    scan_id = str(created["scan_id"])
    print(f"OK accepted scan_id={scan_id}")

    deadline = time.time() + float(args.timeout)
    last_seq = -1
    final: dict | None = None
    while time.time() < deadline:
        code, detail = _request("GET", f"{base}/api/v1/scans/{scan_id}", api_key=api_key)
        if code != 200 or not isinstance(detail, dict):
            print(f"WARN get_scan HTTP {code}: {detail}", file=sys.stderr)
            time.sleep(args.poll_interval)
            continue
        seq = detail.get("progress_seq")
        if seq is not None and int(seq) < last_seq:
            # Stale response — keep previous observation.
            time.sleep(args.poll_interval)
            continue
        if seq is not None:
            last_seq = int(seq)
        final = detail
        status = str(detail.get("status") or "")
        print(
            "progress "
            f"status={status} "
            f"pct={detail.get('progress_percent')} "
            f"stage={detail.get('progress_stage')} "
            f"units={detail.get('progress_current')}/{detail.get('progress_total')} "
            f"calls={detail.get('llm_calls_made')} "
            f"usd_est={detail.get('llm_usd_estimated')} "
            f"batches={detail.get('batches_completed')}/{detail.get('batches_total')} "
            f"job={detail.get('job_status')}"
        )
        if status in TERMINAL:
            break
        time.sleep(args.poll_interval)

    if final is None or str(final.get("status") or "") not in TERMINAL:
        print("FAIL: timeout waiting for terminal scan status", file=sys.stderr)
        return 5

    code, job = _request("GET", f"{base}/api/v1/scans/{scan_id}/job", api_key=api_key)
    print(f"job_status HTTP {code}: {json.dumps(job, default=str)[:2000]}")

    print(
        "RESULT "
        f"status={final.get('status')} "
        f"execution_mode={final.get('execution_mode')} "
        f"outcome={final.get('outcome')} "
        f"result_source={final.get('result_source')} "
        f"llm_calls_made={final.get('llm_calls_made')} "
        f"llm_usd_estimated={final.get('llm_usd_estimated')} "
        f"cost_basis={final.get('cost_basis')} "
        f"provider_successes={final.get('provider_successes')} "
        f"provider_failures={final.get('provider_failures')} "
        f"remediation_eligible={final.get('remediation_eligible')}"
    )

    if final.get("execution_mode") == "real_llm" and int(final.get("llm_calls_made") or 0) < 1:
        print(
            "FAIL: claimed real_llm without llm_calls_made >= 1",
            file=sys.stderr,
        )
        return 6

    print("OK smoke finished (read-only; no GitHub mutation requested)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
