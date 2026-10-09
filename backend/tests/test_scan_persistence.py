"""P1: durable scan integrity persistence and cold-hydration safety."""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from sqlalchemy import JSON, Boolean, Integer, String, Text, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from app.orchestration.scan_persistence import (
    INTEGRITY_VERSION,
    LEGACY_WARNING,
    apply_integrity_to_scan_row,
    unpack_integrity_from_scan_row,
)


class _PersistBase(DeclarativeBase):
    pass


class _IntegrityScanRow(_PersistBase):
    """Minimal disposable table mirroring Scan integrity columns (SQLite-safe)."""

    __tablename__ = "integrity_scan_rows"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    status: Mapped[str] = mapped_column(String(50), default="completed")
    integrity_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    execution_mode: Mapped[str | None] = mapped_column(String(50), nullable=True)
    result_source: Mapped[str | None] = mapped_column(String(50), nullable=True)
    outcome: Mapped[str | None] = mapped_column(String(50), nullable=True)
    score_source: Mapped[str | None] = mapped_column(String(50), nullable=True)
    patches_source: Mapped[str | None] = mapped_column(String(50), nullable=True)
    remediation_eligible: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    intelligence_warnings: Mapped[list | None] = mapped_column(JSON, nullable=True)
    data_source: Mapped[str | None] = mapped_column(String(50), nullable=True)
    llm_calls_made: Mapped[int | None] = mapped_column(Integer, nullable=True)
    dag_evaluations_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    synthetic_intents_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pages_crawled: Mapped[int | None] = mapped_column(Integer, nullable=True)
    dom_chunks_extracted: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


def _real_llm_kwargs() -> dict:
    return {
        "execution_mode": "real_llm",
        "result_source": "real_pipeline",
        "outcome": "success",
        "score_source": "deterministic_scorer",
        "patches_source": "assembler",
        "remediation_eligible": True,
        "intelligence_warnings": ["all stages completed"],
        "llm_calls_made": 31,
        "dag_evaluations_count": 30,
        "synthetic_intents_count": 0,
        "pages_crawled": 3,
        "dom_chunks_extracted": 42,
        "data_source": "live_pipeline",
        "error": None,
    }


def test_apply_sets_integrity_version_and_fields():
    row = SimpleNamespace()
    apply_integrity_to_scan_row(row, **_real_llm_kwargs())
    assert row.integrity_version == INTEGRITY_VERSION
    assert row.execution_mode == "real_llm"
    assert row.remediation_eligible is True
    assert row.intelligence_warnings == ["all stages completed"]
    assert row.dag_evaluations_count == 30
    assert row.synthetic_intents_count == 0


def test_unpack_roundtrip_preserves_contract():
    row = SimpleNamespace()
    apply_integrity_to_scan_row(row, **_real_llm_kwargs())
    restored = unpack_integrity_from_scan_row(row)
    assert restored.is_legacy is False
    assert restored.execution_mode == "real_llm"
    assert restored.result_source == "real_pipeline"
    assert restored.outcome == "success"
    assert restored.score_source == "deterministic_scorer"
    assert restored.patches_source == "assembler"
    assert restored.remediation_eligible is True
    assert restored.intelligence_warnings == ["all stages completed"]
    assert restored.llm_calls_made == 31
    assert restored.dag_evaluations_count == 30
    assert restored.synthetic_intents_count == 0
    assert restored.pages_crawled == 3
    assert restored.dom_chunks_extracted == 42
    assert restored.data_source == "live_pipeline"
    assert restored.integrity_version == INTEGRITY_VERSION


def test_legacy_row_is_inconclusive_not_real_llm():
    legacy = SimpleNamespace(
        status="completed",
        f_score=72.0,
        integrity_version=None,
        execution_mode=None,
        result_source=None,
        outcome=None,
        remediation_eligible=None,
        intelligence_warnings=None,
        llm_calls_made=None,
        pages_crawled=None,
        error=None,
    )
    restored = unpack_integrity_from_scan_row(legacy)
    assert restored.is_legacy is True
    assert restored.execution_mode == "unknown"
    assert restored.result_source == "inconclusive"
    assert restored.outcome == "inconclusive"
    assert restored.remediation_eligible is False
    assert LEGACY_WARNING in restored.intelligence_warnings
    assert restored.data_source == "synthetic_fallback"


def test_missing_integrity_never_defaults_remediation_true():
    blank = SimpleNamespace()
    restored = unpack_integrity_from_scan_row(blank)
    assert restored.remediation_eligible is False
    assert restored.execution_mode != "real_llm"


def test_inconsistent_real_llm_without_result_source_demoted():
    row = SimpleNamespace(
        integrity_version=INTEGRITY_VERSION,
        execution_mode="real_llm",
        result_source=None,
        outcome="success",
        score_source="deterministic_scorer",
        patches_source="assembler",
        remediation_eligible=True,
        intelligence_warnings=[],
        llm_calls_made=10,
        dag_evaluations_count=5,
        synthetic_intents_count=0,
        pages_crawled=1,
        dom_chunks_extracted=2,
        data_source="live_pipeline",
        error=None,
    )
    restored = unpack_integrity_from_scan_row(row)
    assert restored.execution_mode == "unknown"
    assert restored.result_source == "inconclusive"
    assert restored.outcome == "inconclusive"
    assert restored.remediation_eligible is False
    assert any("demoted" in w.lower() for w in restored.intelligence_warnings)


def test_non_real_mode_forces_remediation_false():
    row = SimpleNamespace()
    apply_integrity_to_scan_row(
        row,
        execution_mode="synthetic_fallback",
        result_source="synthetic_fallback",
        outcome="inconclusive",
        score_source="mock",
        patches_source="mock",
        remediation_eligible=True,  # hostile / inconsistent write
        intelligence_warnings=["synthetic fill"],
        llm_calls_made=0,
        dag_evaluations_count=0,
        synthetic_intents_count=30,
        pages_crawled=2,
        dom_chunks_extracted=10,
        data_source="synthetic_fallback",
        error=None,
    )
    # Persist may store the flag; unpack must still gate it.
    restored = unpack_integrity_from_scan_row(row)
    assert restored.execution_mode == "synthetic_fallback"
    assert restored.remediation_eligible is False


def test_warnings_string_coerced_to_list():
    row = SimpleNamespace(
        integrity_version=1,
        execution_mode="deterministic",
        result_source="inconclusive",
        outcome="partial",
        score_source="none",
        patches_source="none",
        remediation_eligible=False,
        intelligence_warnings="single warning",
        llm_calls_made=0,
        dag_evaluations_count=0,
        synthetic_intents_count=0,
        pages_crawled=1,
        dom_chunks_extracted=0,
        data_source="live_pipeline",
        error=None,
    )
    restored = unpack_integrity_from_scan_row(row)
    assert restored.intelligence_warnings == ["single warning"]


def test_integrity_survives_fresh_db_session():
    """Simulate process restart: write in one session, reload in another."""
    engine = create_engine("sqlite:///:memory:")
    _PersistBase.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    scan_id = str(uuid.uuid4())
    kwargs = _real_llm_kwargs()

    with factory() as session:
        with session.begin():
            row = _IntegrityScanRow(id=scan_id, status="completed")
            apply_integrity_to_scan_row(row, **kwargs)
            session.add(row)

    # New session = cold hydration after restart
    with factory() as session:
        loaded = session.get(_IntegrityScanRow, scan_id)
        assert loaded is not None
        restored = unpack_integrity_from_scan_row(loaded)

    assert restored.execution_mode == "real_llm"
    assert restored.result_source == "real_pipeline"
    assert restored.outcome == "success"
    assert restored.remediation_eligible is True
    assert restored.intelligence_warnings == ["all stages completed"]
    assert restored.dag_evaluations_count == 30
    assert restored.synthetic_intents_count == 0
    assert restored.llm_calls_made == 31
    assert restored.pages_crawled == 3
    assert restored.dom_chunks_extracted == 42
    assert restored.score_source == "deterministic_scorer"
    assert restored.patches_source == "assembler"
    assert restored.data_source == "live_pipeline"
    assert restored.integrity_version == INTEGRITY_VERSION

    engine.dispose()


def test_legacy_row_survives_fresh_session_as_unknown():
    engine = create_engine("sqlite:///:memory:")
    _PersistBase.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    scan_id = str(uuid.uuid4())

    with factory() as session:
        with session.begin():
            session.add(_IntegrityScanRow(id=scan_id, status="completed"))

    with factory() as session:
        loaded = session.execute(
            select(_IntegrityScanRow).where(_IntegrityScanRow.id == scan_id)
        ).scalar_one()
        restored = unpack_integrity_from_scan_row(loaded)

    assert restored.is_legacy is True
    assert restored.execution_mode == "unknown"
    assert restored.outcome == "inconclusive"
    assert restored.remediation_eligible is False
    assert LEGACY_WARNING in restored.intelligence_warnings

    engine.dispose()


@pytest.mark.asyncio
async def test_get_scan_cold_hydration_uses_persisted_integrity(monkeypatch):
    """GET /scans/{id} DB path must surface integrity, not invent real_llm."""
    from datetime import UTC, datetime

    from app.api.v1 import scans as scans_mod
    from app.models.database import Scan as ScanModel

    scan_uuid = uuid.uuid4()
    scan_id = f"scan_{scan_uuid.hex}"

    # Clear memory cache so hydration hits DB path
    scans_mod.SCANS_DB.pop(scan_id, None)

    db_scan = ScanModel(
        id=scan_uuid,
        url="https://example.com",
        repo_url=None,
        status="completed",
        f_score=80.0,
        s_ans=80.0,
        s_con=80.0,
        s_str=80.0,
        s_acc=80.0,
        created_at=datetime.now(UTC),
        completed_at=datetime.now(UTC),
    )
    apply_integrity_to_scan_row(db_scan, **_real_llm_kwargs())

    class _Result:
        def __init__(self, items):
            self._items = items

        def scalars(self):
            return self

        def all(self):
            return self._items

    class _Session:
        async def get(self, model, pk):
            if model is ScanModel and pk == scan_uuid:
                return db_scan
            return None

        async def execute(self, _stmt):
            return _Result([])

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

    class _SessionFactory:
        def __call__(self):
            return _Session()

    monkeypatch.setattr(scans_mod, "AsyncSessionLocal", _SessionFactory())

    resp = await scans_mod.get_scan(scan_id)
    assert resp.execution_mode == "real_llm"
    assert resp.result_source == "real_pipeline"
    assert resp.outcome == "success"
    assert resp.remediation_eligible is True
    assert resp.intelligence_warnings == ["all stages completed"]
    assert resp.llm_calls_made == 31
    assert resp.summary is not None
    assert resp.summary.dag_evaluations_count == 30
    assert resp.summary.synthetic_intents_count == 0
    assert resp.summary.pages_crawled == 3
    assert resp.summary.dom_chunks_extracted == 42
    assert resp.data_source == "live_pipeline"

    scans_mod.SCANS_DB.pop(scan_id, None)


@pytest.mark.asyncio
async def test_get_scan_legacy_row_not_presented_as_real(monkeypatch):
    from datetime import UTC, datetime

    from app.api.v1 import scans as scans_mod
    from app.models.database import Scan as ScanModel

    scan_uuid = uuid.uuid4()
    scan_id = f"scan_{scan_uuid.hex}"
    scans_mod.SCANS_DB.pop(scan_id, None)

    db_scan = ScanModel(
        id=scan_uuid,
        url="https://legacy.example",
        status="completed",
        f_score=55.0,
        created_at=datetime.now(UTC),
    )
    # No integrity columns set → legacy

    class _Result:
        def scalars(self):
            return self

        def all(self):
            return []

    class _Session:
        async def get(self, model, pk):
            if model is ScanModel and pk == scan_uuid:
                return db_scan
            return None

        async def execute(self, _stmt):
            return _Result()

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

    class _SessionFactory:
        def __call__(self):
            return _Session()

    monkeypatch.setattr(scans_mod, "AsyncSessionLocal", _SessionFactory())

    resp = await scans_mod.get_scan(scan_id)
    assert resp.execution_mode == "unknown"
    assert resp.result_source == "inconclusive"
    assert resp.outcome == "inconclusive"
    assert resp.remediation_eligible is False
    assert LEGACY_WARNING in resp.intelligence_warnings
    assert resp.data_source != "live_pipeline"

    scans_mod.SCANS_DB.pop(scan_id, None)
