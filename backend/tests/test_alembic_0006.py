"""Smoke-check Alembic revision 0006 identifiers and upgrade ops exist."""

from __future__ import annotations

from pathlib import Path


def test_0006_revision_chain():
    path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "0006_progress_checkpoints.py"
    )
    text = path.read_text(encoding="utf-8")
    assert 'revision: str = "0006_progress_checkpoints"' in text
    assert 'down_revision: str | None = "0005_scan_jobs"' in text
    assert "scan_progress_events" in text
    assert "checkpoint_json" in text
    assert "verification_method" in text
    assert "llm_usd_checkpoint" in text
    assert "progress_percent" in text
