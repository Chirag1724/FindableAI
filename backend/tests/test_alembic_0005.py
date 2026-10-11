"""Alembic revision chain includes 0005_scan_jobs."""

from __future__ import annotations

from pathlib import Path


def test_alembic_0005_revises_0004():
    path = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "0005_scan_jobs.py"
    text = path.read_text(encoding="utf-8")
    assert 'revision: str = "0005_scan_jobs"' in text
    assert 'down_revision: str | None = "0004_remediation_lifecycle"' in text
    assert "scan_jobs" in text
    assert "fencing_token" in text
    assert "idempotency_key" in text
