"""Deterministic pre-mutation patch validation (Stage 4 / Stage 3B).

Never executes model-generated shell. A skipped check is not a passed check.
Safety-critical failures block validated PR creation.
Projected score improvements are never consulted here.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import PurePosixPath
from typing import Any

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

_PATH_TRAVERSAL = re.compile(r"(^|/)\.\.(/|$)")
# Aligned with GitHub PR engine allowlist (html + framework + text manifests).
_ALLOWED_SUFFIXES = (
    ".html",
    ".htm",
    ".json",
    ".jsonld",
    ".txt",
    ".tsx",
    ".jsx",
    ".ts",
    ".js",
)
_FORBIDDEN_PATH_PREFIXES = (
    ".github/workflows/",
    ".github/actions/",
    ".git/",
)
_FORBIDDEN_BASENAMES = frozenset(
    {
        ".env",
        ".env.local",
        ".env.production",
        "credentials.json",
        "service-account.json",
        "id_rsa",
        "id_ed25519",
        "package-lock.json",
        "yarn.lock",
        "pnpm-lock.yaml",
        "poetry.lock",
        "cargo.lock",
        "gemfile.lock",
    }
)
_CONTROL_OR_NUL = re.compile(r"[\x00-\x1f\x7f]")
_SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("private_key_block", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    ("aws_access_key", re.compile(r"AKIA[0-9A-Z]{16}")),
    (
        "github_token",
        re.compile(r"(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9_]{20,}"),
    ),
    (
        "generic_api_key_assignment",
        re.compile(
            r"(?i)(?:api[_-]?key|secret[_-]?key|access[_-]?token)\s*[:=]\s*['\"][^'\"]{16,}['\"]"
        ),
    ),
)
_MAX_PATCH_CHARS = 200_000
_MAX_FILE_CHARS = 2_000_000
_BINARY_NUL = re.compile(r"\x00")


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
    return ValidationCheck(name=name, status=status, detail=detail, safety_critical=safety_critical)


def _normalize_repo_relative(path: str) -> str | None:
    """Return a normalized repo-relative POSIX path, or None if unsafe.

    Platform-independent: does not consult the local filesystem. Rejects UNC,
    drive letters, absolute POSIX, control characters, and traversal.
    """
    if not path or not str(path).strip():
        return None
    raw = str(path).strip().replace("\\", "/")
    if _CONTROL_OR_NUL.search(raw):
        return None
    if raw.startswith("//") or raw.startswith("\\\\"):
        return None
    if raw.startswith("/") or raw.startswith("~") or "://" in raw:
        return None
    if re.match(r"^[a-zA-Z]:", raw):
        return None
    if _PATH_TRAVERSAL.search(raw) or ".." in raw.split("/"):
        return None
    # PurePosixPath resolves ``.`` segments without touching the filesystem.
    resolved = PurePosixPath(raw)
    if resolved.is_absolute() or ".." in resolved.parts:
        return None
    normalized = resolved.as_posix().lstrip("./")
    if not normalized or normalized.startswith("../"):
        return None
    return normalized


def validate_repo_path(path: str) -> ValidationCheck:
    if not path or not str(path).strip():
        return _check("path_present", CheckStatus.FAILED, "empty path", safety_critical=True)
    raw = str(path).strip().replace("\\", "/")
    if _CONTROL_OR_NUL.search(raw):
        return _check(
            "path_safe",
            CheckStatus.FAILED,
            "control/NUL characters rejected",
            safety_critical=True,
        )
    if raw.startswith("//") or raw.startswith("\\\\"):
        return _check("path_safe", CheckStatus.FAILED, "UNC path rejected", safety_critical=True)
    if raw.startswith("/") or raw.startswith("~") or "://" in raw or re.match(r"^[a-zA-Z]:", raw):
        return _check(
            "path_safe", CheckStatus.FAILED, "absolute/URL path rejected", safety_critical=True
        )
    if _PATH_TRAVERSAL.search(raw) or ".." in raw.split("/"):
        return _check(
            "path_traversal", CheckStatus.FAILED, "path traversal rejected", safety_critical=True
        )
    normalized = _normalize_repo_relative(raw)
    if normalized is None:
        return _check(
            "path_safe",
            CheckStatus.FAILED,
            "path failed repository-boundary normalization",
            safety_critical=True,
        )
    lower = normalized.lower()
    basename = PurePosixPath(normalized).name.lower()
    if basename in _FORBIDDEN_BASENAMES or any(
        lower.startswith(prefix) for prefix in _FORBIDDEN_PATH_PREFIXES
    ):
        return _check(
            "path_policy",
            CheckStatus.FAILED,
            f"forbidden path rejected: {normalized}",
            safety_critical=True,
        )
    if not lower.endswith(_ALLOWED_SUFFIXES):
        return _check(
            "path_suffix",
            CheckStatus.FAILED,
            f"unsupported suffix (allowed: {_ALLOWED_SUFFIXES})",
            safety_critical=True,
        )
    return _check("path_safe", CheckStatus.PASSED, normalized)


def validate_no_secrets(patch_text: str) -> ValidationCheck:
    """Reject patches that appear to insert credentials or private key material."""
    text = patch_text or ""
    if _BINARY_NUL.search(text):
        return _check(
            "no_binary",
            CheckStatus.FAILED,
            "NUL byte / binary content rejected",
            safety_critical=True,
        )
    # Prefer added lines so we do not block quotes of existing redacted material in context.
    added = "\n".join(
        line[1:]
        for line in text.splitlines()
        if line.startswith("+") and not line.startswith("+++")
    )
    haystack = added if added.strip() else text
    for label, pattern in _SECRET_PATTERNS:
        if pattern.search(haystack):
            return _check(
                "no_secrets",
                CheckStatus.FAILED,
                f"potential secret material detected ({label})",
                safety_critical=True,
            )
    return _check("no_secrets", CheckStatus.PASSED)


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
        return _check("html_parse", CheckStatus.FAILED, "empty file content", safety_critical=True)
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
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            return _check(
                "jsonld_syntax",
                CheckStatus.FAILED,
                f"invalid JSON-LD: {exc.msg}",
                safety_critical=True,
            )

        items = data if isinstance(data, list) else [data]
        for item in items:
            if not isinstance(item, dict):
                return _check(
                    "jsonld_syntax",
                    CheckStatus.FAILED,
                    "JSON-LD root must be an object or list of objects",
                    safety_critical=True,
                )
            type_val = item.get("@type")
            graph_val = item.get("@graph")
            if not type_val and not graph_val:
                return _check(
                    "jsonld_syntax",
                    CheckStatus.FAILED,
                    "missing '@type' or '@graph' in Schema.org JSON-LD",
                    safety_critical=True,
                )
            if "@context" in item:
                ctx = str(item.get("@context", "")).strip().lower()
                valid_ctx = bool(
                    re.match(r"^https?://(?:www\.)?schema\.org/?$", ctx) or ctx == "schema.org"
                )
                if not valid_ctx:
                    return _check(
                        "jsonld_syntax",
                        CheckStatus.FAILED,
                        "invalid '@context' (must reference schema.org)",
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
    result.checks.append(validate_no_secrets(patch_text))
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
