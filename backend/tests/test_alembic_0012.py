"""Alembic revision chain includes 0012_indexes_and_token_ledger."""

from __future__ import annotations

from pathlib import Path


def test_alembic_0012_revises_0011():
    path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "0012_indexes_and_token_ledger.py"
    )
    text = path.read_text(encoding="utf-8")
    assert 'revision: str = "0012_indexes_and_token_ledger"' in text
    assert 'down_revision: str | None = "0011_organizations_and_api_keys"' in text
    assert "org_token_ledger" in text
    assert "ix_dom_chunks_scan_tsv" in text
    assert "ix_scan_jobs_active_queue" in text
    assert "ix_scans_active" in text
    assert "btree_gin" in text
