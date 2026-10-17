"""Enforce evidence same-scan ownership; align intents.persona with ORM.

Revision ID: 0007_evidence_same_scan
Revises: 0006_progress_checkpoints
Create Date: 2026-10-15 00:00:00.000000

- Adds ``intents.persona`` (present on the SQLAlchemy model, missing from 0001).
- Removes only provably cross-scan ``evidence`` rows (intent.scan_id != chunk.scan_id)
  before installing the trigger — intent rows and valid evidence are preserved.
- Rejects INSERT/UPDATE where the cited DOM chunk belongs to a different scan
  than the intent. Application-layer validation remains the primary gate; the
  trigger is a durable database backstop.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0007_evidence_same_scan"
down_revision: str | None = "0006_progress_checkpoints"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Idempotent: local DBs may already have persona from ORM create_all / partial apply.
    op.execute("ALTER TABLE intents ADD COLUMN IF NOT EXISTS persona VARCHAR(50)")
    # Auditable repair: drop only evidence whose intent and chunk disagree on scan.
    # Valid same-scan evidence and all intent/finding rows are preserved.
    op.execute(
        """
        DELETE FROM evidence AS e
        USING intents AS i, dom_chunks AS c
        WHERE e.intent_id = i.id
          AND e.chunk_id = c.id
          AND i.scan_id <> c.scan_id
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION evidence_same_scan_check()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
          intent_scan uuid;
          chunk_scan uuid;
        BEGIN
          SELECT scan_id INTO intent_scan FROM intents WHERE id = NEW.intent_id;
          SELECT scan_id INTO chunk_scan FROM dom_chunks WHERE id = NEW.chunk_id;
          IF intent_scan IS NULL THEN
            RAISE EXCEPTION 'evidence_same_scan_check: intent % not found', NEW.intent_id;
          END IF;
          IF chunk_scan IS NULL THEN
            RAISE EXCEPTION 'evidence_same_scan_check: chunk % not found', NEW.chunk_id;
          END IF;
          IF intent_scan <> chunk_scan THEN
            RAISE EXCEPTION
              'evidence_same_scan_check: intent scan % != chunk scan %',
              intent_scan, chunk_scan;
          END IF;
          RETURN NEW;
        END;
        $$;
        """
    )
    op.execute("DROP TRIGGER IF EXISTS trg_evidence_same_scan ON evidence")
    op.execute(
        """
        CREATE TRIGGER trg_evidence_same_scan
        BEFORE INSERT OR UPDATE OF intent_id, chunk_id ON evidence
        FOR EACH ROW
        EXECUTE PROCEDURE evidence_same_scan_check();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_evidence_same_scan ON evidence")
    op.execute("DROP FUNCTION IF EXISTS evidence_same_scan_check()")
    op.drop_column("intents", "persona")
