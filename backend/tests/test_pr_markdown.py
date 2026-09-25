"""Unit tests for P2-3.6 PR Markdown generator."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.github.pr_markdown import PRMarkdownError, generate_pr_markdown
from app.schemas.github_pr import PRFileChange, PRReportData
from app.schemas.intelligence import (
    EntailmentStatus,
    EvidenceReference,
    IntentEvaluation,
)


def _report(**overrides: object) -> PRReportData:
    base = dict(
        scan_id="scan-001",
        current_score=42.0,
        projected_score=78.0,
        delta=36.0,
        detected_gaps=["Missing FAQPage"],
        intent_evaluations=[
            IntentEvaluation(
                intent_id="local_01",
                query="Hours?",
                status=EntailmentStatus.UNKNOWN,
                reasoning="gap",
                evidence=[],
                confidence=0.7,
            )
        ],
        evidence_items=[
            EvidenceReference(
                chunk_id="c1",
                dom_path="/main/p[1]",
                url="https://example.com/page",
                excerpt="Open daily 10-10",
            )
        ],
        file_changes=[
            PRFileChange(
                path="index.html",
                summary="Added Schema.org JSON-LD: FAQPage",
                opportunity_ids=["missing_schema:FAQPage"],
                schema_types=["FAQPage"],
            )
        ],
        opportunity_titles=["Add FAQPage schema"],
    )
    base.update(overrides)
    return PRReportData(**base)  # type: ignore[arg-type]


def test_score_and_delta_rendering():
    md = generate_pr_markdown(_report())
    assert "| Current | 42.0 |" in md
    assert "| Projected | 78.0 |" in md
    assert "| Improvement | +36.0 |" in md
    assert "`42.0 → 78.0`" in md
    assert "Delta: `+36.0`" in md


def test_negative_delta():
    md = generate_pr_markdown(_report(current_score=80.0, projected_score=70.0, delta=-10.0))
    assert "Improvement | -10.0 |" in md
    assert "Delta: `-10.0`" in md


def test_detected_gaps_and_empty():
    assert "Missing FAQPage" in generate_pr_markdown(_report())
    md = generate_pr_markdown(_report(detected_gaps=[]))
    assert "None detected" in md


def test_intent_table():
    md = generate_pr_markdown(_report())
    assert "| Intent | Status | Confidence |" in md
    assert "| local_01 | UNKNOWN | 0.70 |" in md


def test_empty_intents():
    md = generate_pr_markdown(_report(intent_evaluations=[]))
    assert "Not available" in md


def test_evidence_fields():
    md = generate_pr_markdown(_report())
    assert "chunk `c1`" in md
    assert "DOM `/main/p[1]`" in md
    assert "https://example.com/page" in md
    assert "Open daily 10-10" in md


def test_no_evidence():
    md = generate_pr_markdown(_report(evidence_items=[]))
    assert "## Evidence" in md
    assert "- Not available" in md


def test_file_changes():
    md = generate_pr_markdown(_report())
    assert "`index.html`" in md
    assert "FAQPage" in md


def test_markdown_special_characters():
    md = generate_pr_markdown(
        _report(
            detected_gaps=["A | B"],
            evidence_items=[
                EvidenceReference(
                    chunk_id="c`x`",
                    dom_path="<div>",
                    excerpt="line1\nline2 | pipe",
                )
            ],
            file_changes=[PRFileChange(path="a.html", summary="uses | and `ticks`")],
        )
    )
    assert "\\|" in md or "A \\| B" in md
    assert "&lt;div&gt;" in md
    assert "line1 line2" in md


def test_secret_redaction_in_evidence():
    md = generate_pr_markdown(
        _report(
            evidence_items=[
                EvidenceReference(
                    chunk_id="c1",
                    dom_path="/p",
                    excerpt="Authorization: Bearer SUPERSECRET",
                )
            ]
        )
    )
    assert "SUPERSECRET" not in md
    assert "[redacted]" in md


def test_deterministic_output():
    a = generate_pr_markdown(_report())
    b = generate_pr_markdown(_report())
    assert a == b
    assert a.endswith("\n")


def test_invalid_input():
    with pytest.raises(PRMarkdownError):
        generate_pr_markdown({"scan_id": "x"})  # type: ignore[arg-type]


def test_delta_validation_on_model():
    with pytest.raises(ValidationError):
        PRReportData(
            scan_id="s",
            current_score=10.0,
            projected_score=20.0,
            delta=5.0,
        )
