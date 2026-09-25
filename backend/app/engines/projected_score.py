"""Projected F-score via in-memory patch simulation (P2-3.4).

Reuses the existing Phase E ``Scorer`` / ``ScoreInputs`` — no formula duplication.

No LLM, network, database, GitHub, or filesystem writes.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import replace

from app.engines.patch_formatter import format_jsonld_patch
from app.engines.scorer import ScoreInputs, Scorer
from app.schemas.patching import (
    FormattedPatch,
    GeneratedJsonLd,
    PatchFormatStatus,
    ProjectedScoreBatchResult,
    ProjectedScoreResult,
)
from app.schemas.scoring import ScoreBreakdown

logger = logging.getLogger(__name__)


class ProjectedScoreError(Exception):
    def __init__(self, message: str, *, reason: str | None = None) -> None:
        self.reason = reason or "projected_score_error"
        super().__init__(message)


def _ensure_breakdown(
    *,
    inputs: ScoreInputs,
    current: ScoreBreakdown | None,
    scorer: Scorer,
) -> ScoreBreakdown:
    if current is not None:
        return current
    return scorer.score(inputs)


def simulate_html_with_patch(
    html: str,
    generated: GeneratedJsonLd,
    *,
    file_path: str = "index.html",
) -> tuple[str, FormattedPatch]:
    """Return in-memory patched HTML + formatter metadata (no disk I/O)."""
    formatted = format_jsonld_patch(generated, html=html, file_path=file_path)
    if formatted.status is PatchFormatStatus.APPLIED:
        if formatted.patched_html is None:
            raise ProjectedScoreError(
                "formatter applied but patched_html missing",
                reason="invalid_simulation",
            )
        return formatted.patched_html, formatted
    if formatted.status is PatchFormatStatus.NOOP:
        return html, formatted
    raise ProjectedScoreError(
        f"cannot simulate patch ({formatted.status.value}): {formatted.message}",
        reason=formatted.status.value,
    )


def project_score_for_generated(
    generated: GeneratedJsonLd,
    *,
    score_inputs: ScoreInputs,
    current_breakdown: ScoreBreakdown | None = None,
    html_document_index: int = 0,
    file_path: str = "index.html",
    scorer: Scorer | None = None,
) -> ProjectedScoreResult:
    """Project F-score for a single generated JSON-LD opportunity independently."""
    engine = scorer or Scorer()
    current = _ensure_breakdown(inputs=score_inputs, current=current_breakdown, scorer=engine)

    documents = list(score_inputs.html_documents)
    if not documents:
        # Minimal document so schema injection has a home.
        documents = ["<!DOCTYPE html><html><head></head><body></body></html>"]
        base_inputs = replace(score_inputs, html_documents=documents)
        current = engine.score(base_inputs)
    else:
        base_inputs = score_inputs

    if html_document_index < 0 or html_document_index >= len(documents):
        raise ProjectedScoreError(
            f"html_document_index {html_document_index} out of range",
            reason="invalid_simulation",
        )

    original_html = documents[html_document_index]
    original_snapshot = original_html
    patched_html, formatted = simulate_html_with_patch(
        original_html,
        generated,
        file_path=file_path,
    )

    # Caller-supplied documents must remain untouched.
    if score_inputs.html_documents:
        if list(score_inputs.html_documents)[html_document_index] != original_snapshot:
            raise ProjectedScoreError(
                "simulation mutated source html_documents",
                reason="mutation_detected",
            )

    new_documents = list(base_inputs.html_documents) if base_inputs.html_documents else []
    if not new_documents:
        new_documents = [patched_html]
    else:
        new_documents[html_document_index] = patched_html

    projected_inputs = replace(base_inputs, html_documents=new_documents)
    projected = engine.score(projected_inputs)

    delta = projected.f_score - current.f_score
    logger.info(
        "Projected score opportunity=%s current=%.4f projected=%.4f delta=%.4f",
        generated.opportunity_id,
        current.f_score,
        projected.f_score,
        delta,
    )
    return ProjectedScoreResult(
        opportunity_id=generated.opportunity_id,
        schema_type=generated.schema_type,
        current_score=current.f_score,
        projected_score=projected.f_score,
        delta=delta,
        current_breakdown=current,
        projected_breakdown=projected,
        patch_reference=formatted.file_path,
    )


def project_scores(
    generated: Sequence[GeneratedJsonLd],
    *,
    score_inputs: ScoreInputs,
    current_breakdown: ScoreBreakdown | None = None,
    html_document_index: int = 0,
    file_path: str = "index.html",
    scorer: Scorer | None = None,
) -> ProjectedScoreBatchResult:
    """Independent (non-cumulative) projections for each generated payload."""
    engine = scorer or Scorer()
    current = _ensure_breakdown(inputs=score_inputs, current=current_breakdown, scorer=engine)
    projections: list[ProjectedScoreResult] = []
    for item in sorted(generated, key=lambda g: g.opportunity_id):
        projections.append(
            project_score_for_generated(
                item,
                score_inputs=score_inputs,
                current_breakdown=current,
                html_document_index=html_document_index,
                file_path=file_path,
                scorer=engine,
            )
        )
    return ProjectedScoreBatchResult(projections=projections)


class ProjectedScoreCalculator:
    def project(
        self,
        generated: Sequence[GeneratedJsonLd],
        *,
        score_inputs: ScoreInputs,
        current_breakdown: ScoreBreakdown | None = None,
        html_document_index: int = 0,
        file_path: str = "index.html",
    ) -> ProjectedScoreBatchResult:
        return project_scores(
            generated,
            score_inputs=score_inputs,
            current_breakdown=current_breakdown,
            html_document_index=html_document_index,
            file_path=file_path,
        )
