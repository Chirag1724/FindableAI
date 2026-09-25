"""Deterministic PR Markdown generator (P2-3.6).

Pure reporting layer — no GitHub, network, filesystem, database, or LLM.
"""

from __future__ import annotations

import re

from app.schemas.github_pr import PRFileChange, PRReportData
from app.schemas.intelligence import EvidenceReference, IntentEvaluation

_MAX_EVIDENCE_SNIPPET = 200
_SECRET_HINTS = re.compile(r"(?i)(api[_-]?key|token|secret|password|authorization|bearer\s+\S+)")


class PRMarkdownError(Exception):
    def __init__(self, message: str, *, reason: str | None = None) -> None:
        self.reason = reason or "pr_markdown_error"
        super().__init__(message)


def _escape_cell(value: str) -> str:
    """Escape text for Markdown table cells."""
    text = value.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\n", " ").replace("|", "\\|").replace("`", "\\`")
    text = text.replace("<", "&lt;").replace(">", "&gt;")
    return text.strip()


def _escape_inline(value: str) -> str:
    return value.replace("`", "\\`").replace("<", "&lt;").replace(">", "&gt;")


def _fmt_score(value: float) -> str:
    return f"{value:.1f}"


def _fmt_delta(value: float) -> str:
    sign = "+" if value >= 0 else ""
    return f"{sign}{value:.1f}"


def _snippet(text: str | None) -> str:
    if text is None:
        return "Not available"
    cleaned = " ".join(text.split())
    if _SECRET_HINTS.search(cleaned):
        return "[redacted]"
    if len(cleaned) > _MAX_EVIDENCE_SNIPPET:
        return cleaned[: _MAX_EVIDENCE_SNIPPET - 3] + "..."
    return cleaned or "Not available"


def _gap_lines(gaps: list[str]) -> list[str]:
    if not gaps:
        return ["- None detected"]
    return [f"- {_escape_inline(g)}" for g in gaps]


def _intent_rows(evaluations: list[IntentEvaluation]) -> list[str]:
    rows = [
        "| Intent | Status | Confidence |",
        "|---|---|---:|",
    ]
    if not evaluations:
        rows.append("| Not available | — | — |")
        return rows
    for item in sorted(evaluations, key=lambda e: e.intent_id):
        rows.append(
            "| {intent} | {status} | {conf} |".format(
                intent=_escape_cell(item.intent_id),
                status=_escape_cell(item.status.value),
                conf=f"{item.confidence:.2f}",
            )
        )
    return rows


def _evidence_blocks(items: list[EvidenceReference]) -> list[str]:
    if not items:
        return ["- Not available"]
    lines: list[str] = []
    ordered = sorted(items, key=lambda e: (e.chunk_id, e.dom_path or ""))
    for ref in ordered:
        parts = [f"chunk `{_escape_inline(ref.chunk_id)}`"]
        if ref.dom_path:
            parts.append(f"DOM `{_escape_inline(ref.dom_path)}`")
        if ref.url:
            parts.append(f"URL {_escape_inline(ref.url)}")
        excerpt = _snippet(ref.excerpt)
        lines.append(f"- {', '.join(parts)} — {excerpt}")
    return lines


def _file_rows(changes: list[PRFileChange]) -> list[str]:
    rows = [
        "| File | Changes |",
        "|---|---|",
    ]
    if not changes:
        rows.append("| Not available | — |")
        return rows
    for item in sorted(changes, key=lambda c: c.path):
        rows.append(f"| `{_escape_cell(item.path)}` | {_escape_cell(item.summary)} |")
    return rows


def generate_pr_markdown(report_data: PRReportData) -> str:
    """Render a deterministic PR body from authoritative Phase 3.4+ inputs."""
    if not isinstance(report_data, PRReportData):
        raise PRMarkdownError("report_data must be PRReportData", reason="invalid_input")

    current = _fmt_score(report_data.current_score)
    projected = _fmt_score(report_data.projected_score)
    delta = _fmt_delta(report_data.delta)

    lines: list[str] = [
        "# FindableAI Remediation Report",
        "",
        f"Scan ID: `{_escape_inline(report_data.scan_id)}`",
        "",
        "## Score",
        "",
        "| Metric | Score |",
        "|---|---:|",
        f"| Current | {current} |",
        f"| Projected | {projected} |",
        f"| Improvement | {delta} |",
        "",
        "## Projected Improvement",
        "",
        f"`{current} → {projected}`",
        "",
        f"Delta: `{delta}`",
        "",
        "## Detected Gaps",
        "",
        *_gap_lines(list(report_data.detected_gaps)),
        "",
        "## Intent Evaluation",
        "",
        *_intent_rows(list(report_data.intent_evaluations)),
        "",
        "## Evidence",
        "",
        *_evidence_blocks(list(report_data.evidence_items)),
        "",
        "## Files Changed",
        "",
        *_file_rows(list(report_data.file_changes)),
        "",
    ]

    if report_data.opportunity_titles:
        lines.extend(["## Remediation Opportunities", ""])
        for title in report_data.opportunity_titles:
            lines.append(f"- {_escape_inline(title)}")
        lines.append("")

    body = "\n".join(lines)
    if not body.endswith("\n"):
        body += "\n"
    return body
