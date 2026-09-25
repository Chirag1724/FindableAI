"""Deterministic unified-diff patch formatter (P2-3.3).

Converts GeneratedJsonLd into application/ld+json script insertions.
Does not decide schema content, score, or prioritize.

No LLM, network, database, GitHub, or filesystem writes.
"""

from __future__ import annotations

import difflib
import hashlib
import json
import logging
import re
from collections.abc import Sequence

from app.engines.jsonld_generator import dumps_jsonld
from app.engines.scorer import LOCAL_BUSINESS_SUBTYPES
from app.schemas.patching import (
    FormattedPatch,
    GeneratedJsonLd,
    PatchFormatResult,
    PatchFormatStatus,
    SchemaRemediationTarget,
)

logger = logging.getLogger(__name__)

_SCRIPT_TYPE = 'type="application/ld+json"'
_HEAD_CLOSE = re.compile(r"</head\s*>", re.IGNORECASE)
_BODY_CLOSE = re.compile(r"</body\s*>", re.IGNORECASE)


class PatchFormatterError(Exception):
    def __init__(self, message: str, *, reason: str | None = None) -> None:
        self.reason = reason or "patch_formatter_error"
        super().__init__(message)


def wrap_jsonld_script(json_text: str) -> str:
    body = json_text if json_text.endswith("\n") else json_text + "\n"
    return f"<script {_SCRIPT_TYPE}>\n{body}</script>\n"


def _strip_context(payload: dict) -> dict:
    return {k: v for k, v in payload.items() if k != "@context"}


def _canonical_payload(payload: dict) -> str:
    return json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _payload_fingerprint(payload: dict) -> str:
    return hashlib.sha256(_canonical_payload(_strip_context(payload)).encode("utf-8")).hexdigest()


def _extract_jsonld_blocks(html: str) -> list[dict]:
    pattern = re.compile(
        r"<script\b[^>]*type\s*=\s*[\"']application/ld\+json[\"'][^>]*>(.*?)</script>",
        re.IGNORECASE | re.DOTALL,
    )
    blocks: list[dict] = []
    for match in pattern.finditer(html):
        raw = match.group(1).strip()
        if not raw:
            continue
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            blocks.append(parsed)
        elif isinstance(parsed, list):
            for item in parsed:
                if isinstance(item, dict):
                    blocks.append(item)
    return blocks


def _node_types(node: dict) -> set[str]:
    value = node.get("@type")
    if isinstance(value, str):
        return {value.rsplit("/", 1)[-1]}
    if isinstance(value, list):
        return {str(v).rsplit("/", 1)[-1] for v in value}
    return set()


def _block_matches_target(node: dict, target: SchemaRemediationTarget) -> bool:
    types = _node_types(node)
    if target is SchemaRemediationTarget.LOCAL_BUSINESS:
        return bool(types & LOCAL_BUSINESS_SUBTYPES) or any(t.endswith("Business") for t in types)
    if target is SchemaRemediationTarget.MENU:
        return "Menu" in types or "MenuSection" in types or node.get("hasMenu") is not None
    return target.value in types


def _find_insertion_index(html: str) -> tuple[int, str]:
    head = _HEAD_CLOSE.search(html)
    if head:
        return head.start(), "before_head"
    body = _BODY_CLOSE.search(html)
    if body:
        return body.start(), "before_body"
    raise PatchFormatterError(
        "HTML lacks </head> and </body>; cannot insert safely",
        reason="missing_insertion_point",
    )


def _unified_diff(original: str, patched: str, *, file_path: str) -> str:
    old_lines = original.splitlines(keepends=True)
    new_lines = patched.splitlines(keepends=True)
    diff_iter = difflib.unified_diff(
        old_lines,
        new_lines,
        fromfile=f"a/{file_path}",
        tofile=f"b/{file_path}",
        lineterm="\n",
    )
    return "".join(diff_iter)


def _count_changed_lines(diff_text: str) -> int:
    return sum(
        1
        for line in diff_text.splitlines()
        if (line.startswith("+") and not line.startswith("+++"))
        or (line.startswith("-") and not line.startswith("---"))
    )


def format_jsonld_patch(
    generated: GeneratedJsonLd,
    *,
    html: str,
    file_path: str = "index.html",
) -> FormattedPatch:
    """Insert generated JSON-LD into HTML and produce a unified diff."""
    if not isinstance(html, str):
        raise PatchFormatterError("html must be a string", reason="invalid_html")

    target = generated.schema_type
    new_fp = _payload_fingerprint(dict(generated.payload))

    for existing in _extract_jsonld_blocks(html):
        if not _block_matches_target(existing, target):
            continue
        if _payload_fingerprint(existing) == new_fp:
            return FormattedPatch(
                opportunity_id=generated.opportunity_id,
                schema_type=target,
                file_path=file_path,
                patch_text="",
                changed_lines=0,
                insertion_location="existing",
                is_noop=True,
                status=PatchFormatStatus.NOOP,
                message="identical JSON-LD already present",
                patched_html=html,
            )
        return FormattedPatch(
            opportunity_id=generated.opportunity_id,
            schema_type=target,
            file_path=file_path,
            patch_text="",
            changed_lines=0,
            insertion_location="existing",
            is_noop=False,
            status=PatchFormatStatus.CONFLICT,
            message=(f"conflicting existing {target.value} JSON-LD block; refusing to overwrite"),
            patched_html=None,
        )

    try:
        index, location = _find_insertion_index(html)
    except PatchFormatterError as exc:
        return FormattedPatch(
            opportunity_id=generated.opportunity_id,
            schema_type=target,
            file_path=file_path,
            status=PatchFormatStatus.ERROR,
            message=str(exc),
        )

    script = wrap_jsonld_script(generated.json_text or dumps_jsonld(dict(generated.payload)))
    prefix = html[:index]
    suffix = html[index:]
    insertion = script if prefix.endswith("\n") or not prefix else "\n" + script
    patched = prefix + insertion + suffix
    diff_text = _unified_diff(html, patched, file_path=file_path)

    return FormattedPatch(
        opportunity_id=generated.opportunity_id,
        schema_type=target,
        file_path=file_path,
        patch_text=diff_text,
        changed_lines=_count_changed_lines(diff_text),
        insertion_location=location,
        is_noop=False,
        status=PatchFormatStatus.APPLIED,
        message="json-ld script inserted",
        patched_html=patched,
    )


class PatchFormatter:
    def format_all(
        self,
        generated: Sequence[GeneratedJsonLd],
        *,
        html: str,
        file_path: str = "index.html",
    ) -> PatchFormatResult:
        ordered = sorted(generated, key=lambda g: g.opportunity_id)
        patches = [format_jsonld_patch(item, html=html, file_path=file_path) for item in ordered]
        logger.info("Formatted %d JSON-LD patches", len(patches))
        return PatchFormatResult(patches=patches)


def format_patches(
    generated: Sequence[GeneratedJsonLd],
    *,
    html: str,
    file_path: str = "index.html",
) -> PatchFormatResult:
    return PatchFormatter().format_all(generated, html=html, file_path=file_path)
