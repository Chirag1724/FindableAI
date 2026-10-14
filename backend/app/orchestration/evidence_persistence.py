"""Persist and hydrate evaluation evidence linked to real DOM chunks (Phase 2 Stage 2).

Only writes rows when the cited chunk_id resolves to a persisted DOMChunk for the scan.
Never invents evidence for synthetic/demo evaluations. LLM citations are untrusted input
until they resolve to same-scan durable rows.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models.database import DOMChunk as DOMChunkModel
from app.models.database import Evidence as EvidenceModel
from app.schemas.intelligence import EntailmentStatus, EvidenceReference, IntentEvaluation

logger = logging.getLogger(__name__)

OBSERVATION_SCAN = "scan"
OBSERVATION_VERIFICATION = "verification"
ROLE_SUPPORTING = "supporting"
ROLE_CONTRADICTING = "contradicting"
ROLE_CITED = "cited"

ALLOWED_ROLES = frozenset({ROLE_SUPPORTING, ROLE_CONTRADICTING, ROLE_CITED})
ALLOWED_PHASES = frozenset({OBSERVATION_SCAN, OBSERVATION_VERIFICATION})

_EVIDENCE_VALIDATION_SUFFIX = (
    " [Evidence validation failed: cited chunk references could not be "
    "resolved to persisted same-scan DOM chunks; status downgraded.]"
)
_PERSISTENCE_FAILURE_SUFFIX = (
    " [Evidence persistence unavailable: citations were not durably validated; "
    "status downgraded.]"
)
_HYDRATION_FAILURE_SUFFIX = (
    " [Evidence hydration unavailable: stored evidence could not be loaded; "
    "status downgraded for this response.]"
)

HYDRATE_WARN = (
    "Persisted evidence could not be hydrated for this request; "
    "evidence-backed statuses were downgraded and remediation is not eligible."
)
PERSISTENCE_FAIL_WARN = (
    "Evidence persistence failed; intent statuses were downgraded because "
    "citations were not durably validated."
)
NO_DURABLE_EVIDENCE_REMEDIATION_WARN = (
    "Remediation eligibility cleared: no evidence-backed findings remain after "
    "durable citation validation."
)


def evaluations_have_evidence_backed_findings(
    evaluations: Sequence[IntentEvaluation],
) -> bool:
    """True when at least one finding is non-UNKNOWN with durable evidence cites.

    Invariant: remediation may only remain eligible when this is True **and** the
    pre-evidence integrity decision already authorized remediation. UUID version
    checks alone are not sufficient — cites must have passed persistence integrity.
    """
    for evaluation in evaluations:
        if evaluation.status is EntailmentStatus.UNKNOWN:
            continue
        if evaluation.evidence:
            return True
    return False


def refine_remediation_eligible(
    base_eligible: bool,
    evaluations: Sequence[IntentEvaluation],
) -> bool:
    """Intersect pipeline integrity eligibility with post-evidence final state.

    Does not invent eligibility: ``base_eligible`` must already be True from
    ``decide_scan_integrity``. Clears eligibility when no evidence-backed
    findings survive sanitization/hydration integrity.
    """
    if not base_eligible:
        return False
    return evaluations_have_evidence_backed_findings(evaluations)


@dataclass
class EvidenceBuildResult:
    """Outcome of mapping evaluation citations to durable Evidence rows."""

    rows: list[EvidenceModel] = field(default_factory=list)
    citation_count: int = 0
    persisted_count: int = 0
    unresolved_count: int = 0
    cross_scan_count: int = 0


def is_non_durable_chunk_uuid(value: uuid.UUID) -> bool:
    """True for UUID5 ids used by memory-fallback retrieval (never durable PKs).

    Persisted ``DOMChunk.id`` values are UUID4 (ORM default). Memory-fallback
    retrieval assigns UUID5 ids via ``ephemeral_memory_chunk_id``. Version-5
    citations must not justify evidence-backed findings.
    """
    return value.version == 5


def _parse_chunk_uuid(raw: str | None) -> uuid.UUID | None:
    if not raw or not isinstance(raw, str):
        return None
    text = raw.strip()
    if text.startswith("chunk_"):
        # Index-style ids are temporary orchestration labels, not durable FK targets.
        return None
    try:
        parsed = uuid.UUID(text)
    except (ValueError, AttributeError, TypeError):
        return None
    if is_non_durable_chunk_uuid(parsed):
        return None
    return parsed


def evidence_role_for_status(status: Any) -> str:
    value = status.value if hasattr(status, "value") else str(status)
    if value == "CONTRADICTED":
        return ROLE_CONTRADICTING
    if value in ("SUPPORTED", "PARTIALLY_SUPPORTED"):
        return ROLE_SUPPORTING
    return ROLE_CITED


def evidence_persistence_warning(total_cites: int, persisted: int) -> str | None:
    """Honest warning when evaluation cites could not be stored as Evidence rows."""
    if total_cites <= 0:
        return None
    if persisted <= 0:
        return (
            "Evaluation citations could not be linked to persisted DOM chunks; "
            "no evidence rows were stored for cold hydration."
        )
    if persisted < total_cites:
        return (
            f"Only {persisted} of {total_cites} evaluation citations were persisted as evidence; "
            "unresolved temporary or unknown chunk references were skipped."
        )
    return None


async def load_chunk_id_map(session: Any, scan_id: uuid.UUID) -> dict[uuid.UUID, DOMChunkModel]:
    """Map persisted DOMChunk.id → row for the scan (scan-scoped)."""
    result = await session.execute(select(DOMChunkModel).where(DOMChunkModel.scan_id == scan_id))
    rows = result.scalars().all()
    return {row.id: row for row in rows}


def build_evidence_rows_for_intent(
    *,
    intent_id: uuid.UUID,
    evaluation: IntentEvaluation,
    chunk_map: dict[uuid.UUID, DOMChunkModel],
    observation_phase: str = OBSERVATION_SCAN,
    intent_scan_id: uuid.UUID | None = None,
) -> EvidenceBuildResult:
    """Create Evidence ORM rows for one evaluation; skips unresolved citations.

    When ``intent_scan_id`` is provided, chunks whose ``scan_id`` differs are
    rejected (cross-scan cite) even if present in ``chunk_map``.
    """
    result = EvidenceBuildResult()
    refs = list(evaluation.evidence or [])
    result.citation_count = len(refs)
    if not refs:
        return result

    if observation_phase not in ALLOWED_PHASES:
        observation_phase = OBSERVATION_SCAN

    role = evidence_role_for_status(evaluation.status)
    if role not in ALLOWED_ROLES:
        role = ROLE_CITED

    seen: set[uuid.UUID] = set()
    for idx, ref in enumerate(refs):
        chunk_uuid = _parse_chunk_uuid(getattr(ref, "chunk_id", None))
        if chunk_uuid is None:
            result.unresolved_count += 1
            continue
        if chunk_uuid in seen:
            # Duplicate cite of same chunk for this intent — keep first rank only.
            result.unresolved_count += 1
            continue
        chunk = chunk_map.get(chunk_uuid)
        if chunk is None:
            logger.debug(
                "Skipping evidence cite: chunk %s not in scan chunk map for intent %s",
                ref.chunk_id,
                intent_id,
            )
            result.unresolved_count += 1
            continue
        chunk_scan = getattr(chunk, "scan_id", None)
        if intent_scan_id is not None and chunk_scan is not None and chunk_scan != intent_scan_id:
            logger.warning(
                "Rejecting cross-scan evidence cite chunk=%s chunk_scan=%s intent_scan=%s",
                chunk_uuid,
                chunk_scan,
                intent_scan_id,
            )
            result.cross_scan_count += 1
            result.unresolved_count += 1
            continue
        seen.add(chunk_uuid)
        rank = ref.rank if isinstance(ref.rank, int) and ref.rank >= 1 else idx + 1
        excerpt = ref.excerpt
        if excerpt is None and chunk.content:
            excerpt = chunk.content if len(chunk.content) <= 280 else f"{chunk.content[:277]}..."
        dom_path = getattr(ref, "dom_path", None) or chunk.dom_path
        result.rows.append(
            EvidenceModel(
                id=uuid.uuid4(),
                intent_id=intent_id,
                chunk_id=chunk_uuid,
                rank=rank,
                rrf_score=ref.rrf_score,
                source_url=ref.url or chunk.url,
                excerpt=excerpt,
                dom_path=dom_path,
                evidence_role=role,
                observation_phase=observation_phase,
            )
        )
    result.persisted_count = len(result.rows)
    return result


def evidence_refs_from_rows(rows: list[EvidenceModel]) -> list[EvidenceReference]:
    """Map durable Evidence ORM rows to API EvidenceReference (stable ordering)."""
    ordered = sorted(
        rows,
        key=lambda r: (int(getattr(r, "rank", 0) or 0), str(getattr(r, "chunk_id", ""))),
    )
    refs: list[EvidenceReference] = []
    for row in ordered:
        dom_path = getattr(row, "dom_path", None) or "(unknown)"
        refs.append(
            EvidenceReference(
                chunk_id=str(row.chunk_id),
                dom_path=dom_path,
                url=getattr(row, "source_url", None),
                rank=row.rank,
                rrf_score=row.rrf_score,
                excerpt=getattr(row, "excerpt", None),
            )
        )
    return refs


def _append_suffix(reasoning: str, suffix: str) -> str:
    text = (reasoning or "").strip()
    if suffix not in text:
        text = (text + suffix)[:4000]
    return text


def apply_persisted_evidence_integrity(
    evaluation: IntentEvaluation,
    built: EvidenceBuildResult,
) -> IntentEvaluation:
    """Reconcile a finding with durable evidence mapping at the backend boundary.

    - Retains only citations that mapped to persisted same-scan chunks.
    - Downgrades non-UNKNOWN findings with zero durable evidence to UNKNOWN.
    - Never represents unresolved/malformed/cross-scan cites as verified evidence.
    Does not claim semantic entailment beyond citation association checks.
    """
    durable = evidence_refs_from_rows(built.rows)
    status = evaluation.status
    reasoning = (evaluation.reasoning or "").strip()
    confidence = float(evaluation.confidence)

    if status is EntailmentStatus.UNKNOWN:
        return evaluation.model_copy(update={"evidence": [], "reasoning": reasoning})

    if built.persisted_count <= 0:
        reasoning = _append_suffix(reasoning, _EVIDENCE_VALIDATION_SUFFIX)
        return evaluation.model_copy(
            update={
                "status": EntailmentStatus.UNKNOWN,
                "evidence": [],
                "reasoning": reasoning,
                "confidence": min(confidence, 0.25),
            }
        )

    return evaluation.model_copy(update={"evidence": durable, "reasoning": reasoning})


def downgrade_unvalidated_evaluations(
    evaluations: Sequence[IntentEvaluation],
    *,
    reason: Literal["persistence", "hydration", "missing_evidence"] = "persistence",
) -> list[IntentEvaluation]:
    """Downgrade evidence-backed findings when durable validation is unavailable.

    Preserves query/category/persona/reasoning (with an honest suffix) and clears
    evidence. Used for persistence failure, hydration failure, and successful
    hydrate that returned no evidence for a non-UNKNOWN status.
    """
    if reason == "persistence":
        suffix = _PERSISTENCE_FAILURE_SUFFIX
    elif reason == "hydration":
        suffix = _HYDRATION_FAILURE_SUFFIX
    else:
        suffix = _EVIDENCE_VALIDATION_SUFFIX

    out: list[IntentEvaluation] = []
    for evaluation in evaluations:
        if evaluation.status is EntailmentStatus.UNKNOWN:
            out.append(
                evaluation.model_copy(
                    update={"evidence": [], "reasoning": (evaluation.reasoning or "").strip()}
                )
            )
            continue
        # Non-UNKNOWN without durable validation cannot remain evidence-backed.
        reasoning = _append_suffix(evaluation.reasoning or "", suffix)
        out.append(
            evaluation.model_copy(
                update={
                    "status": EntailmentStatus.UNKNOWN,
                    "evidence": [],
                    "reasoning": reasoning,
                    "confidence": min(float(evaluation.confidence), 0.25),
                }
            )
        )
    return out


def apply_response_evidence_integrity(
    evaluations: Sequence[IntentEvaluation],
    *,
    hydrate_failed: bool,
) -> list[IntentEvaluation]:
    """Response-boundary integrity after attempting evidence hydration.

    - ``hydrate_failed``: infrastructure failure — downgrade all evidence-backed
      statuses (do not present empty evidence as successful verification).
    - Hydrate succeeded: non-UNKNOWN with empty evidence is treated as missing
      durable support and downgraded (distinct from intentional UNKNOWN).
    """
    if hydrate_failed:
        return downgrade_unvalidated_evaluations(evaluations, reason="hydration")

    out: list[IntentEvaluation] = []
    for evaluation in evaluations:
        if evaluation.status is EntailmentStatus.UNKNOWN:
            out.append(
                evaluation.model_copy(
                    update={"evidence": [], "reasoning": (evaluation.reasoning or "").strip()}
                )
            )
            continue
        if not evaluation.evidence:
            out.extend(
                downgrade_unvalidated_evaluations([evaluation], reason="missing_evidence")
            )
            continue
        out.append(evaluation)
    return out


async def hydrate_evidence_for_intents(
    session: Any,
    intent_rows: list[Any],
) -> dict[uuid.UUID, list[EvidenceReference]]:
    """Load Evidence (+ chunk when available) for intent ids → EvidenceReference lists."""
    if not intent_rows:
        return {}
    intent_ids = [it.id for it in intent_rows]
    result = await session.execute(
        select(EvidenceModel)
        .where(EvidenceModel.intent_id.in_(intent_ids))
        .options(selectinload(EvidenceModel.chunk))
        .order_by(EvidenceModel.rank.asc(), EvidenceModel.chunk_id.asc())
    )
    evidence_rows = result.scalars().all()
    out: dict[uuid.UUID, list[EvidenceReference]] = {iid: [] for iid in intent_ids}
    for ev in evidence_rows:
        chunk = getattr(ev, "chunk", None)
        chunk_id = str(chunk.id) if chunk is not None else str(ev.chunk_id)
        dom_path = getattr(ev, "dom_path", None) or (chunk.dom_path if chunk is not None else None)
        if not dom_path:
            # Cannot satisfy EvidenceReference.dom_path without inventing a path.
            logger.debug(
                "Skipping hydrate for evidence %s: missing dom_path",
                getattr(ev, "id", None),
            )
            continue
        source_url = ev.source_url or (chunk.url if chunk is not None else None)
        out.setdefault(ev.intent_id, []).append(
            EvidenceReference(
                chunk_id=chunk_id,
                dom_path=dom_path,
                url=source_url,
                rank=ev.rank,
                rrf_score=ev.rrf_score,
                excerpt=ev.excerpt,
            )
        )
    return out
