"""Persist and hydrate evaluation evidence linked to real DOM chunks (Phase 2 Stage 2).

Only writes rows when the cited chunk_id resolves to a persisted DOMChunk for the scan.
Never invents evidence for synthetic/demo evaluations.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models.database import DOMChunk as DOMChunkModel
from app.models.database import Evidence as EvidenceModel
from app.schemas.intelligence import EvidenceReference, IntentEvaluation

logger = logging.getLogger(__name__)

OBSERVATION_SCAN = "scan"
OBSERVATION_VERIFICATION = "verification"
ROLE_SUPPORTING = "supporting"
ROLE_CONTRADICTING = "contradicting"
ROLE_CITED = "cited"

ALLOWED_ROLES = frozenset({ROLE_SUPPORTING, ROLE_CONTRADICTING, ROLE_CITED})
ALLOWED_PHASES = frozenset({OBSERVATION_SCAN, OBSERVATION_VERIFICATION})


@dataclass
class EvidenceBuildResult:
    """Outcome of mapping evaluation citations to durable Evidence rows."""

    rows: list[EvidenceModel] = field(default_factory=list)
    citation_count: int = 0
    persisted_count: int = 0
    unresolved_count: int = 0


def _parse_chunk_uuid(raw: str | None) -> uuid.UUID | None:
    if not raw or not isinstance(raw, str):
        return None
    text = raw.strip()
    if text.startswith("chunk_"):
        # Index-style ids are temporary orchestration labels, not durable FK targets.
        return None
    try:
        return uuid.UUID(text)
    except (ValueError, AttributeError, TypeError):
        return None


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
) -> EvidenceBuildResult:
    """Create Evidence ORM rows for one evaluation; skips unresolved citations."""
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
        .order_by(EvidenceModel.rank.asc())
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
