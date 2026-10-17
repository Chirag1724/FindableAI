"""Stage 2 hardening: persistence/hydration failure honesty + ephemeral UUID5 cites."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.crawler.search import ephemeral_memory_chunk_id, store_dom_chunks
from app.orchestration.evidence_persistence import (
    HYDRATE_WARN,
    NO_DURABLE_EVIDENCE_REMEDIATION_WARN,
    PERSISTENCE_FAIL_WARN,
    apply_persisted_evidence_integrity,
    apply_response_evidence_integrity,
    build_evidence_rows_for_intent,
    downgrade_unvalidated_evaluations,
    is_non_durable_chunk_uuid,
    refine_remediation_eligible,
)
from app.core.auth import TenantContext
from app.schemas.intelligence import (
    EntailmentStatus,
    EvidenceReference,
    IntentCategory,
    IntentEvaluation,
)


def _supported_eval(*, chunk_id: str) -> IntentEvaluation:
    return IntentEvaluation(
        intent_id="intent_h",
        query="What are the hours?",
        status=EntailmentStatus.SUPPORTED,
        reasoning="Cited chunk supports hours.",
        confidence=0.92,
        category=IntentCategory.AVAILABILITY,
        evidence=[EvidenceReference(chunk_id=chunk_id, dom_path="main > p", rank=1, excerpt="9-5")],
    )


def test_uuid5_memory_fallback_ids_are_non_durable():
    scan = uuid.uuid4()
    ephemeral = ephemeral_memory_chunk_id(scan, 0, "office hours monday")
    assert ephemeral.version == 5
    assert is_non_durable_chunk_uuid(ephemeral)
    durable = uuid.uuid4()
    assert durable.version == 4
    assert not is_non_durable_chunk_uuid(durable)


def test_memory_fallback_uuid5_cite_cannot_persist_or_stay_supported():
    scan_id = uuid.uuid4()
    intent_id = uuid.uuid4()
    ephemeral = ephemeral_memory_chunk_id(scan_id, 0, "hours text")
    # Even if stuffed into chunk_map, UUID5 cites are rejected at parse time.
    chunk_map = {
        ephemeral: SimpleNamespace(
            id=ephemeral,
            scan_id=scan_id,
            url="https://ex.com",
            dom_path="main > p",
            content="hours text",
        )
    }
    evaluation = _supported_eval(chunk_id=str(ephemeral))
    built = build_evidence_rows_for_intent(
        intent_id=intent_id,
        evaluation=evaluation,
        chunk_map=chunk_map,
        intent_scan_id=scan_id,
    )
    assert built.persisted_count == 0
    assert built.unresolved_count == 1
    clean = apply_persisted_evidence_integrity(evaluation, built)
    assert clean.status is EntailmentStatus.UNKNOWN
    assert clean.evidence == []
    assert "Evidence validation failed" in clean.reasoning


def test_downgrade_unvalidated_on_persistence_failure_preserves_query():
    evaluation = _supported_eval(chunk_id=str(uuid.uuid4()))
    out = downgrade_unvalidated_evaluations([evaluation], reason="persistence")
    assert len(out) == 1
    assert out[0].status is EntailmentStatus.UNKNOWN
    assert out[0].evidence == []
    assert out[0].query == evaluation.query
    assert out[0].category == evaluation.category
    assert "Evidence persistence unavailable" in out[0].reasoning
    assert out[0].confidence <= 0.25


def test_response_integrity_hydration_failure_downgrades_and_clears_evidence():
    evaluation = _supported_eval(chunk_id=str(uuid.uuid4()))
    # Simulate hydrate failure: empty evidence list with stale SUPPORTED status.
    stale = evaluation.model_copy(update={"evidence": []})
    out = apply_response_evidence_integrity([stale], hydrate_failed=True)
    assert out[0].status is EntailmentStatus.UNKNOWN
    assert out[0].evidence == []
    assert "Evidence hydration unavailable" in out[0].reasoning


def test_response_integrity_successful_hydrate_empty_evidence_downgrades():
    evaluation = _supported_eval(chunk_id=str(uuid.uuid4())).model_copy(update={"evidence": []})
    out = apply_response_evidence_integrity([evaluation], hydrate_failed=False)
    assert out[0].status is EntailmentStatus.UNKNOWN
    assert out[0].evidence == []


def test_response_integrity_unknown_with_empty_evidence_unchanged():
    evaluation = IntentEvaluation(
        intent_id="u1",
        query="Anything?",
        status=EntailmentStatus.UNKNOWN,
        reasoning="No evidence retrieved.",
        confidence=0.1,
        category=IntentCategory.POLICY,
        evidence=[],
    )
    out = apply_response_evidence_integrity([evaluation], hydrate_failed=False)
    assert out[0].status is EntailmentStatus.UNKNOWN
    assert out[0].evidence == []
    assert "downgraded" not in out[0].reasoning.lower()


@pytest.mark.asyncio
async def test_store_dom_chunks_rejects_wrong_embedding_dimensions():
    from app.crawler.dom_chunker import ChunkData

    scan_id = uuid.uuid4()
    chunks = [
        ChunkData(
            url="https://ex.com",
            dom_path="main > p",
            content="Hello world content for embedding.",
            tag="p",
            word_count=5,
        )
    ]
    bad_emb = [0.1] * 8  # not EMBEDDING_DIM
    session = AsyncMock()
    session.add_all = MagicMock()
    session.flush = AsyncMock()

    with patch(
        "app.core.embeddings.get_embeddings_batch",
        new=AsyncMock(return_value=[bad_emb]),
    ):
        rows = await store_dom_chunks(scan_id, chunks, session=session)

    assert len(rows) == 1
    assert rows[0].embedding is None
    session.add_all.assert_called_once()
    session.flush.assert_awaited()


def test_refine_remediation_eligible_requires_evidence_backed_findings():
    from app.orchestration.evidence_persistence import EvidenceBuildResult

    assert (
        refine_remediation_eligible(False, [_supported_eval(chunk_id=str(uuid.uuid4()))]) is False
    )
    supported = _supported_eval(chunk_id=str(uuid.uuid4()))
    assert refine_remediation_eligible(True, [supported]) is True
    unknown_only = apply_persisted_evidence_integrity(
        supported, EvidenceBuildResult(citation_count=1, persisted_count=0, unresolved_count=1)
    )
    assert unknown_only.status is EntailmentStatus.UNKNOWN
    assert refine_remediation_eligible(True, [unknown_only]) is False
    assert "Remediation eligibility cleared" in NO_DURABLE_EVIDENCE_REMEDIATION_WARN


@pytest.mark.asyncio
async def test_run_scan_pipeline_persistence_failure_downgrades_and_disables_remediation():
    """Real pipeline path: persistence boom must not publish SUPPORTED / eligible."""
    from datetime import UTC, datetime

    from app.api.v1 import scans as scans_module
    from app.orchestration.result import OrchestrationResult
    from app.orchestration.scan_integrity import (
        ExecutionMode,
        IntegrityDecision,
        PatchesSource,
        ResultSource,
        ScanOutcome,
        ScoreSource,
    )
    from app.orchestration.state import ScanPhase
    from app.schemas.scan import ScanResponse, ScanStatus

    scan_uuid = uuid.uuid4()
    scan_id = f"scan_{scan_uuid.hex[:12]}"
    cite_id = uuid.uuid4()
    supported = _supported_eval(chunk_id=str(cite_id))

    scans_module.SCANS_DB[scan_id] = ScanResponse(
        scan_id=scan_id,
        target_url="https://example.com/pipeline-persist",
        status=ScanStatus.PENDING,
        created_at=datetime.now(UTC),
        intents=[],
        remediation_eligible=True,
    )
    for key in (str(scan_uuid), scan_uuid.hex):
        scans_module.SCANS_DB.pop(key, None)

    class _FakeDAG:
        def __init__(self, **_kwargs):
            pass

        async def run(self, _obs):
            return OrchestrationResult(
                scan_id=str(scan_uuid),
                final_state=ScanPhase.STOP,
                success=True,
                evaluations=[supported],
                evaluation_count=1,
                intent_count=1,
            )

    class _FakeCrawler:
        def __init__(self, **_kwargs):
            pass

        async def crawl(self, _url):
            return []

    eligible_decision = IntegrityDecision(
        execution_mode=ExecutionMode.REAL_LLM,
        data_source="live_pipeline",
        result_source=ResultSource.REAL_PIPELINE,
        score_source=ScoreSource.DETERMINISTIC_SCORER,
        patches_source=PatchesSource.ASSEMBLER,
        outcome=ScanOutcome.SUCCESS,
        remediation_eligible=True,
        warnings=[],
    )

    emitted: list[str] = []

    async def _capture_emit(scan_id_arg, status_val, percent, step_name, message, **kwargs):
        status_text = getattr(status_val, "value", str(status_val))
        emitted.append(f"{status_text}|{step_name}|{message}")
        # Keep progress fields updated without durable progress DB.
        if scan_id_arg in scans_module.SCANS_DB:
            rec = scans_module.SCANS_DB[scan_id_arg]
            rec.status = status_val
            rec.progress_percent = percent
            rec.progress_stage = step_name
            rec.progress_message = message
        from app.schemas.scan import ScanStatusEvent

        return ScanStatusEvent(
            scan_id=scan_id_arg,
            status=status_val,
            progress_percent=percent,
            current_step=step_name,
            message=message,
            timestamp=datetime.now(UTC),
        )

    class _FailPersistSession:
        """Forces the durable persist boundary to fail (real except path)."""

        async def __aenter__(self):
            raise RuntimeError("forced durable evidence persistence failure")

        async def __aexit__(self, *_a):
            return False

    try:
        with (
            patch.object(scans_module, "FindableAIDAG", _FakeDAG),
            patch.object(scans_module, "AsyncCrawler", _FakeCrawler),
            patch.object(scans_module, "AsyncSessionLocal", lambda: _FailPersistSession()),
            patch.object(scans_module, "store_dom_chunks", AsyncMock(return_value=[])),
            patch.object(scans_module, "decide_scan_integrity", return_value=eligible_decision),
            patch.object(scans_module, "_emit_event", _capture_emit),
            patch.object(scans_module, "LighthouseEngine", side_effect=RuntimeError("skip lh")),
            patch(
                "app.jobs.checkpoints.best_effort_save_checkpoint",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "app.jobs.execution_context.get_job_execution_context",
                return_value=None,
            ),
        ):
            await scans_module.run_scan_pipeline(
                scan_id,
                scan_uuid,
                "https://example.com/pipeline-persist",
                1,
                personas=["cto"],
            )

        record = scans_module.SCANS_DB[scan_id]
        assert record.intents, "pipeline must publish intents"
        assert all(i.status is EntailmentStatus.UNKNOWN for i in record.intents)
        assert all(i.evidence == [] for i in record.intents)
        assert record.remediation_eligible is False
        assert PERSISTENCE_FAIL_WARN in (record.intelligence_warnings or [])
        assert any("Audit Complete" in msg for msg in emitted)
        assert any("|completed|" in msg or msg.startswith("completed|") for msg in emitted)
        # Completion event must not claim a successful real_llm remediation posture.
        assert not any("SUPPORTED" in msg for msg in emitted)
    finally:
        scans_module.SCANS_DB.pop(scan_id, None)
        for key in (str(scan_uuid), scan_uuid.hex, f"scan_{scan_uuid.hex}"):
            scans_module.SCANS_DB.pop(key, None)
            scans_module.CHUNKS_DB.pop(key, None)
            scans_module.HTML_DB.pop(key, None)
            scans_module.EVENT_LOGS.pop(key, None)


@pytest.mark.asyncio
async def test_get_intents_cold_hydrate_and_hydrate_failure(monkeypatch):
    from starlette.requests import Request

    from app.api.v1 import scans as scans_module

    scan_uuid = uuid.uuid4()
    scan_id = str(scan_uuid)
    intent_id = uuid.uuid4()
    chunk_id = uuid.uuid4()

    # Ensure cold path (no process-local intents).
    scans_module.SCANS_DB.pop(scan_id, None)

    intent_row = SimpleNamespace(
        id=intent_id,
        query="Hours?",
        category="availability",
        persona="cto",
        status="SUPPORTED",
        reasoning="Supported by chunk.",
        confidence=0.9,
    )
    db_scan = SimpleNamespace(id=scan_uuid, org_id=None, url="https://example.com")

    class _Scalars:
        def __init__(self, rows):
            self._rows = rows

        def all(self):
            return self._rows

    class _Result:
        def __init__(self, rows):
            self._rows = rows

        def scalars(self):
            return _Scalars(self._rows)

    class _Session:
        async def get(self, _model, _id):
            return db_scan

        async def execute(self, _stmt):
            return _Result([intent_row])

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

    class _SessionFactory:
        def __call__(self):
            return _Session()

    monkeypatch.setattr(scans_module, "AsyncSessionLocal", _SessionFactory())
    monkeypatch.setattr(scans_module, "resolve_scan_uuid", lambda _sid: scan_uuid)

    req = Request({"type": "http", "headers": [], "method": "GET", "path": "/"})
    req.state.tenant = TenantContext(is_system_admin=True)

    # Successful hydrate
    async def _hydrate_ok(_session, _rows):
        return {
            intent_id: [
                EvidenceReference(
                    chunk_id=str(chunk_id),
                    dom_path="main > p",
                    rank=1,
                    excerpt="Open 9-5",
                    url="https://ex.com",
                )
            ]
        }

    monkeypatch.setattr(scans_module, "hydrate_evidence_for_intents", _hydrate_ok)
    ok = await scans_module.get_scan_intents(scan_id, req)
    assert len(ok) == 1
    assert ok[0]["status"] == "SUPPORTED"
    assert len(ok[0]["evidence"]) == 1
    assert ok[0]["evidence"][0]["chunk_id"] == str(chunk_id)

    # Hydrate failure → downgrade
    async def _hydrate_boom(_session, _rows):
        raise RuntimeError("hydrate exploded")

    monkeypatch.setattr(scans_module, "hydrate_evidence_for_intents", _hydrate_boom)
    failed = await scans_module.get_scan_intents(scan_id, req)
    assert len(failed) == 1
    assert failed[0]["status"] == "UNKNOWN"
    assert failed[0]["evidence"] == []
    assert "hydration unavailable" in failed[0]["reasoning"].lower()


@pytest.mark.asyncio
async def test_get_scan_hydration_failure_clears_remediation_eligible(monkeypatch):
    from datetime import UTC, datetime

    from app.api.v1 import scans as scans_module

    scan_uuid = uuid.uuid4()
    scan_id = str(scan_uuid)
    scans_module.SCANS_DB.pop(scan_id, None)

    intent_id = uuid.uuid4()
    intent_row = SimpleNamespace(
        id=intent_id,
        query="Hours?",
        category="availability",
        persona="cto",
        status="SUPPORTED",
        reasoning="Supported by chunk.",
        confidence=0.9,
    )
    db_scan = SimpleNamespace(
        id=scan_uuid,
        url="https://example.com",
        status="completed",
        created_at=datetime.now(UTC),
        completed_at=datetime.now(UTC),
        f_score=None,
        s_ans=None,
        s_con=None,
        s_str=None,
        s_acc=None,
        repo_url=None,
        progress_percent=100,
        progress_stage="done",
        progress_message="done",
        progress_current=1,
        progress_total=1,
        execution_mode="real_llm",
        result_source="dag",
        outcome="success",
        score_source="deterministic_scorer",
        patches_source="none",
        remediation_eligible=True,
        intelligence_warnings=[],
        llm_calls_made=3,
        data_source="crawl",
        error=None,
        dag_evaluations_count=1,
        synthetic_intents_count=0,
        pages_crawled=1,
        dom_chunks_extracted=2,
    )

    class _Scalars:
        def __init__(self, rows):
            self._rows = rows

        def all(self):
            return self._rows

        def first(self):
            return self._rows[0] if self._rows else None

    class _Result:
        def __init__(self, rows):
            self._rows = rows

        def scalars(self):
            return _Scalars(self._rows)

        def first(self):
            return self._rows[0] if self._rows else None

    class _Session:
        async def get(self, _model, _id):
            return db_scan

        async def execute(self, stmt):
            # Return intents for IntentModel queries; empty for others.
            text = str(stmt)
            if "intents" in text.lower() or "Intent" in text:
                return _Result([intent_row])
            return _Result([])

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

    class _SessionFactory:
        def __call__(self):
            return _Session()

    monkeypatch.setattr(scans_module, "AsyncSessionLocal", _SessionFactory())
    monkeypatch.setattr(scans_module, "resolve_scan_uuid", lambda _sid: scan_uuid)

    async def _hydrate_boom(_session, _rows):
        raise RuntimeError("hydrate exploded")

    monkeypatch.setattr(scans_module, "hydrate_evidence_for_intents", _hydrate_boom)

    monkeypatch.setattr(
        scans_module,
        "unpack_integrity_from_scan_row",
        lambda row: SimpleNamespace(
            execution_mode=row.execution_mode,
            result_source=row.result_source,
            outcome=row.outcome,
            score_source=row.score_source,
            patches_source=row.patches_source,
            remediation_eligible=True,
            intelligence_warnings=list(row.intelligence_warnings or []),
            llm_calls_made=row.llm_calls_made,
            data_source=row.data_source,
            error=row.error,
            dag_evaluations_count=row.dag_evaluations_count,
            synthetic_intents_count=row.synthetic_intents_count,
            pages_crawled=row.pages_crawled,
            dom_chunks_extracted=row.dom_chunks_extracted,
        ),
    )
    monkeypatch.setattr(
        scans_module,
        "enrich_patches_with_framework",
        lambda patches, _repo: patches,
    )

    resp = await scans_module.get_scan_for_tenant(scan_id, TenantContext(is_system_admin=True))
    assert resp.remediation_eligible is False
    assert HYDRATE_WARN in (resp.intelligence_warnings or [])
    assert len(resp.intents) == 1
    assert resp.intents[0].status is EntailmentStatus.UNKNOWN
    assert resp.intents[0].evidence == []


@pytest.mark.asyncio
async def test_get_scan_clears_remediation_when_evidence_missing_after_hydrate(monkeypatch):
    """Stale remediation_eligible must not survive successful hydrate with empty evidence."""
    from datetime import UTC, datetime

    from app.api.v1 import scans as scans_module

    scan_uuid = uuid.uuid4()
    scan_id = str(scan_uuid)
    scans_module.SCANS_DB.pop(scan_id, None)
    intent_id = uuid.uuid4()
    intent_row = SimpleNamespace(
        id=intent_id,
        query="Hours?",
        category="availability",
        persona="cto",
        status="SUPPORTED",
        reasoning="Supported by chunk.",
        confidence=0.9,
    )
    db_scan = SimpleNamespace(
        id=scan_uuid,
        url="https://example.com",
        status="completed",
        created_at=datetime.now(UTC),
        completed_at=datetime.now(UTC),
        f_score=None,
        s_ans=None,
        s_con=None,
        s_str=None,
        s_acc=None,
        repo_url=None,
        progress_percent=100,
        progress_stage="done",
        progress_message="done",
        progress_current=1,
        progress_total=1,
        execution_mode="real_llm",
        result_source="real_pipeline",
        outcome="success",
        score_source="deterministic_scorer",
        patches_source="assembler",
        remediation_eligible=True,
        intelligence_warnings=[],
        llm_calls_made=3,
        data_source="live_pipeline",
        error=None,
        dag_evaluations_count=1,
        synthetic_intents_count=0,
        pages_crawled=1,
        dom_chunks_extracted=2,
        integrity_version=1,
    )

    class _Scalars:
        def __init__(self, rows):
            self._rows = rows

        def all(self):
            return self._rows

    class _Result:
        def __init__(self, rows):
            self._rows = rows

        def scalars(self):
            return _Scalars(self._rows)

    class _Session:
        async def get(self, _model, _id):
            return db_scan

        async def execute(self, stmt):
            text = str(stmt)
            if "intents" in text.lower() or "Intent" in text:
                return _Result([intent_row])
            return _Result([])

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

    class _SessionFactory:
        def __call__(self):
            return _Session()

    monkeypatch.setattr(scans_module, "AsyncSessionLocal", _SessionFactory())
    monkeypatch.setattr(scans_module, "resolve_scan_uuid", lambda _sid: scan_uuid)

    async def _hydrate_empty(_session, _rows):
        return {intent_id: []}

    monkeypatch.setattr(scans_module, "hydrate_evidence_for_intents", _hydrate_empty)
    monkeypatch.setattr(
        scans_module,
        "unpack_integrity_from_scan_row",
        lambda row: SimpleNamespace(
            execution_mode=row.execution_mode,
            result_source=row.result_source,
            outcome=row.outcome,
            score_source=row.score_source,
            patches_source=row.patches_source,
            remediation_eligible=True,
            intelligence_warnings=[],
            llm_calls_made=row.llm_calls_made,
            data_source=row.data_source,
            error=row.error,
            dag_evaluations_count=row.dag_evaluations_count,
            synthetic_intents_count=row.synthetic_intents_count,
            pages_crawled=row.pages_crawled,
            dom_chunks_extracted=row.dom_chunks_extracted,
        ),
    )
    monkeypatch.setattr(
        scans_module,
        "enrich_patches_with_framework",
        lambda patches, _repo: patches,
    )

    resp = await scans_module.get_scan_for_tenant(scan_id, TenantContext(is_system_admin=True))
    assert resp.intents[0].status is EntailmentStatus.UNKNOWN
    assert resp.intents[0].evidence == []
    assert resp.remediation_eligible is False
    assert NO_DURABLE_EVIDENCE_REMEDIATION_WARN in (resp.intelligence_warnings or [])


@pytest.mark.asyncio
async def test_get_scan_keeps_remediation_when_evidence_hydrates(monkeypatch):
    from datetime import UTC, datetime

    from app.api.v1 import scans as scans_module

    scan_uuid = uuid.uuid4()
    scan_id = str(scan_uuid)
    scans_module.SCANS_DB.pop(scan_id, None)
    intent_id = uuid.uuid4()
    chunk_id = uuid.uuid4()
    intent_row = SimpleNamespace(
        id=intent_id,
        query="Hours?",
        category="availability",
        persona="cto",
        status="SUPPORTED",
        reasoning="Supported by chunk.",
        confidence=0.9,
    )
    db_scan = SimpleNamespace(
        id=scan_uuid,
        url="https://example.com",
        status="completed",
        created_at=datetime.now(UTC),
        completed_at=datetime.now(UTC),
        f_score=None,
        s_ans=None,
        s_con=None,
        s_str=None,
        s_acc=None,
        repo_url=None,
        progress_percent=100,
        progress_stage="done",
        progress_message="done",
        progress_current=1,
        progress_total=1,
        execution_mode="real_llm",
        result_source="real_pipeline",
        outcome="success",
        score_source="deterministic_scorer",
        patches_source="assembler",
        remediation_eligible=True,
        intelligence_warnings=[],
        llm_calls_made=3,
        data_source="live_pipeline",
        error=None,
        dag_evaluations_count=1,
        synthetic_intents_count=0,
        pages_crawled=1,
        dom_chunks_extracted=2,
        integrity_version=1,
    )

    class _Scalars:
        def __init__(self, rows):
            self._rows = rows

        def all(self):
            return self._rows

    class _Result:
        def __init__(self, rows):
            self._rows = rows

        def scalars(self):
            return _Scalars(self._rows)

    class _Session:
        async def get(self, _model, _id):
            return db_scan

        async def execute(self, stmt):
            text = str(stmt)
            if "intents" in text.lower() or "Intent" in text:
                return _Result([intent_row])
            return _Result([])

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

    class _SessionFactory:
        def __call__(self):
            return _Session()

    monkeypatch.setattr(scans_module, "AsyncSessionLocal", _SessionFactory())
    monkeypatch.setattr(scans_module, "resolve_scan_uuid", lambda _sid: scan_uuid)

    async def _hydrate_ok(_session, _rows):
        return {
            intent_id: [
                EvidenceReference(
                    chunk_id=str(chunk_id),
                    dom_path="main > p",
                    rank=1,
                    excerpt="Open 9-5",
                )
            ]
        }

    monkeypatch.setattr(scans_module, "hydrate_evidence_for_intents", _hydrate_ok)
    monkeypatch.setattr(
        scans_module,
        "unpack_integrity_from_scan_row",
        lambda row: SimpleNamespace(
            execution_mode=row.execution_mode,
            result_source=row.result_source,
            outcome=row.outcome,
            score_source=row.score_source,
            patches_source=row.patches_source,
            remediation_eligible=True,
            intelligence_warnings=[],
            llm_calls_made=row.llm_calls_made,
            data_source=row.data_source,
            error=row.error,
            dag_evaluations_count=row.dag_evaluations_count,
            synthetic_intents_count=row.synthetic_intents_count,
            pages_crawled=row.pages_crawled,
            dom_chunks_extracted=row.dom_chunks_extracted,
        ),
    )
    monkeypatch.setattr(
        scans_module,
        "enrich_patches_with_framework",
        lambda patches, _repo: patches,
    )

    resp = await scans_module.get_scan_for_tenant(scan_id, TenantContext(is_system_admin=True))
    assert resp.intents[0].status is EntailmentStatus.SUPPORTED
    assert len(resp.intents[0].evidence) == 1
    assert resp.remediation_eligible is True
