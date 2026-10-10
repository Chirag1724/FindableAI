"""Deterministic pre-mutation patch validation (Stage 4).

Never executes model-generated shell. A skipped check is not a passed check.
Safety-critical failures block validated PR creation.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

_PATH_TRAVERSAL = re.compile(r"(^|/)\.\.(/|$)")
_ALLOWED_SUFFIXES = (".html", ".htm", ".json", ".jsonld")
_MAX_PATCH_CHARS = 200_000
_MAX_FILE_CHARS = 2_000_000


class CheckStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    INCONCLUSIVE = "inconclusive"


@dataclass
class ValidationCheck:
    name: str
    status: CheckStatus
    detail: str = ""
    safety_critical: bool = False


@dataclass
class PatchValidationResult:
    checks: list[ValidationCheck] = field(default_factory=list)
    eligible_for_validated_pr: bool = False

    @property
    def failed_critical(self) -> bool:
        return any(
            c.safety_critical and c.status in (CheckStatus.FAILED, CheckStatus.INCONCLUSIVE)
            for c in self.checks
        )

    def as_dicts(self) -> list[dict[str, Any]]:
        return [
            {
                "name": c.name,
                "status": c.status.value,
                "detail": c.detail,
                "safety_critical": c.safety_critical,
            }
            for c in self.checks
        ]


def _check(
    name: str,
    status: CheckStatus,
    detail: str = "",
    *,
    safety_critical: bool = False,
) -> ValidationCheck:
    return ValidationCheck(
        name=name, status=status, detail=detail, safety_critical=safety_critical
    )


def validate_repo_path(path: str) -> ValidationCheck:
    if not path or not str(path).strip():
        return _check("path_present", CheckStatus.FAILED, "empty path", safety_critical=True)
    raw = str(path).strip().replace("\\", "/")
    if raw.startswith("/") or raw.startswith("~") or "://" in raw:
        return _check(
            "path_safe", CheckStatus.FAILED, "absolute/URL path rejected", safety_critical=True
        )
    if _PATH_TRAVERSAL.search(raw) or ".." in raw.split("/"):
        return _check(
            "path_traversal", CheckStatus.FAILED, "path traversal rejected", safety_critical=True
        )
    lower = raw.lower()
    if not lower.endswith(_ALLOWED_SUFFIXES):
        return _check(
            "path_suffix",
            CheckStatus.FAILED,
            f"unsupported suffix (allowed: {_ALLOWED_SUFFIXES})",
            safety_critical=True,
        )
    return _check("path_safe", CheckStatus.PASSED, raw)


def validate_patch_size(patch_text: str) -> ValidationCheck:
    n = len(patch_text or "")
    if n == 0:
        return _check("patch_nonempty", CheckStatus.FAILED, "empty patch", safety_critical=True)
    if n > _MAX_PATCH_CHARS:
        return _check(
            "patch_size",
            CheckStatus.FAILED,
            f"patch too large ({n} chars)",
            safety_critical=True,
        )
    return _check("patch_size", CheckStatus.PASSED, f"{n} chars")


def validate_html_document(content: str) -> ValidationCheck:
    if not content or not content.strip():
        return _check(
            "html_parse", CheckStatus.FAILED, "empty file content", safety_critical=True
        )
    if len(content) > _MAX_FILE_CHARS:
        return _check(
            "html_size",
            CheckStatus.FAILED,
            f"file too large ({len(content)} chars)",
            safety_critical=True,
        )
    try:
        soup = BeautifulSoup(content, "lxml")
        if soup.find("html") is None and soup.find("body") is None and soup.find("head") is None:
            return _check(
                "html_parse",
                CheckStatus.INCONCLUSIVE,
                "no html/head/body nodes found",
                safety_critical=True,
            )
        return _check("html_parse", CheckStatus.PASSED, "parsed")
    except Exception as exc:
        return _check(
            "html_parse",
            CheckStatus.FAILED,
            f"{type(exc).__name__}",
            safety_critical=True,
        )


def validate_jsonld_scripts(html: str) -> ValidationCheck:
    """Validate application/ld+json script bodies if present."""
    try:
        soup = BeautifulSoup(html or "", "lxml")
    except Exception as exc:
        return _check(
            "jsonld_syntax",
            CheckStatus.FAILED,
            f"html parse error: {type(exc).__name__}",
            safety_critical=True,
        )
    scripts = soup.find_all("script", attrs={"type": re.compile(r"ld\+json", re.I)})
    if not scripts:
        return _check(
            "jsonld_syntax",
            CheckStatus.SKIPPED,
            "no JSON-LD scripts in document",
        )
    for script in scripts:
        raw = script.string or script.get_text() or ""
        if not raw.strip():
            return _check(
                "jsonld_syntax",
                CheckStatus.FAILED,
                "empty JSON-LD script",
                safety_critical=True,
            )
        try:
            json.loads(raw)
        except json.JSONDecodeError as exc:
            return _check(
                "jsonld_syntax",
                CheckStatus.FAILED,
                f"invalid JSON-LD: {exc.msg}",
                safety_critical=True,
            )
    return _check("jsonld_syntax", CheckStatus.PASSED, f"{len(scripts)} script(s)")


def validate_not_synthetic(is_synthetic: bool) -> ValidationCheck:
    if is_synthetic:
        return _check(
            "not_synthetic",
            CheckStatus.FAILED,
            "synthetic/mock patch cannot authorize mutation",
            safety_critical=True,
        )
    return _check("not_synthetic", CheckStatus.PASSED)


def validate_evidence_grounding(
    *,
    evidence_chunk_ids: list[str] | None,
    known_scan_chunk_ids: set[str] | None,
) -> ValidationCheck:
    """Require at least one persisted evidence cite belonging to the scan when known."""
    cites = [c for c in (evidence_chunk_ids or []) if c and not str(c).startswith("chunk_")]
    if not cites:
        return _check(
            "evidence_grounding",
            CheckStatus.FAILED,
            "no durable evidence citations for this diagnosis",
            safety_critical=True,
        )
    if known_scan_chunk_ids is None:
        return _check(
            "evidence_grounding",
            CheckStatus.INCONCLUSIVE,
            "scan chunk set unavailable; cannot confirm cite ownership",
            safety_critical=True,
        )
    if not known_scan_chunk_ids:
        return _check(
            "evidence_grounding",
            CheckStatus.FAILED,
            "scan has no persisted chunks",
            safety_critical=True,
        )
    owned = [c for c in cites if c in known_scan_chunk_ids]
    if not owned:
        return _check(
            "evidence_grounding",
            CheckStatus.FAILED,
            "cited chunks do not belong to this scan",
            safety_critical=True,
        )
    return _check("evidence_grounding", CheckStatus.PASSED, f"{len(owned)} owned cite(s)")


def validate_base_content_match(
    *,
    expected_snippet: str | None,
    current_content: str | None,
) -> ValidationCheck:
    """Detect obviously stale base when an original snippet was captured."""
    if not expected_snippet or not expected_snippet.strip():
        return _check(
            "base_freshness",
            CheckStatus.SKIPPED,
            "no original snippet to compare",
        )
    if current_content is None:
        return _check(
            "base_freshness",
            CheckStatus.INCONCLUSIVE,
            "current file content unavailable",
            safety_critical=True,
        )
    needle = expected_snippet.strip()
    if needle and needle not in current_content:
        return _check(
            "base_freshness",
            CheckStatus.FAILED,
            "original snippet not found in current file (stale base)",
            safety_critical=True,
        )
    return _check("base_freshness", CheckStatus.PASSED)


def validate_patch_candidate(
    *,
    file_path: str,
    patch_text: str,
    is_synthetic: bool = False,
    current_file_content: str | None = None,
    original_snippet: str | None = None,
    evidence_chunk_ids: list[str] | None = None,
    known_scan_chunk_ids: set[str] | None = None,
    require_evidence: bool = True,
) -> PatchValidationResult:
    """Run deterministic validators. Critical fail/inconclusive blocks validated PR."""
    result = PatchValidationResult()
    result.checks.append(validate_not_synthetic(is_synthetic))
    result.checks.append(validate_repo_path(file_path))
    result.checks.append(validate_patch_size(patch_text))
    if require_evidence:
        result.checks.append(
            validate_evidence_grounding(
                evidence_chunk_ids=evidence_chunk_ids,
                known_scan_chunk_ids=known_scan_chunk_ids,
            )
        )
    else:
        result.checks.append(
            _check(
                "evidence_grounding",
                CheckStatus.SKIPPED,
                "evidence check not required for this path",
            )
        )

    if current_file_content is not None:
        lower = file_path.lower()
        if lower.endswith((".html", ".htm")):
            result.checks.append(validate_html_document(current_file_content))
            result.checks.append(validate_jsonld_scripts(current_file_content))
        elif lower.endswith((".json", ".jsonld")):
            try:
                json.loads(current_file_content)
                result.checks.append(_check("json_parse", CheckStatus.PASSED))
            except json.JSONDecodeError as exc:
                result.checks.append(
                    _check(
                        "json_parse",
                        CheckStatus.FAILED,
                        exc.msg,
                        safety_critical=True,
                    )
                )
        result.checks.append(
            validate_base_content_match(
                expected_snippet=original_snippet,
                current_content=current_file_content,
            )
        )
    else:
        result.checks.append(
            _check(
                "file_content",
                CheckStatus.INCONCLUSIVE,
                "current repository file not fetched",
                safety_critical=True,
            )
        )

    result.eligible_for_validated_pr = not result.failed_critical
    return result
