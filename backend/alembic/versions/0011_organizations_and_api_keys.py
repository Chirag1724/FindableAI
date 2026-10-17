"""Enterprise multi-tenancy: organizations, memberships, api_keys, and scans.org_id.

Revision ID: 0011_organizations_and_api_keys
Revises: 0010_intent_key_and_partial
Create Date: 2026-10-17 18:15:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0011_organizations_and_api_keys"
down_revision: str | None = "0010_intent_key_and_partial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    uuid_type = sa.UUID().with_variant(postgresql.UUID(as_uuid=True), "postgresql")

    op.create_table(
        "organizations",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("slug", sa.String(length=100), nullable=False),
        sa.Column("plan_tier", sa.String(length=50), nullable=False, server_default="free"),
        sa.Column("rate_limit_per_min", sa.Integer(), nullable=False, server_default="60"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_organizations_slug", "organizations", ["slug"], unique=True)

    op.create_table(
        "org_memberships",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column(
            "org_id",
            uuid_type,
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("user_id", uuid_type, nullable=False),
        sa.Column("role", sa.String(length=50), nullable=False, server_default="member"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_org_memberships_org_id", "org_memberships", ["org_id"])
    op.create_index("ix_org_memberships_user_id", "org_memberships", ["user_id"])

    op.create_table(
        "api_keys",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column(
            "org_id",
            uuid_type,
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("key_prefix", sa.String(length=16), nullable=False),
        sa.Column("hashed_key", sa.String(length=128), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("rate_limit_per_min", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_api_keys_org_id", "api_keys", ["org_id"])
    op.create_index("ix_api_keys_hashed_key", "api_keys", ["hashed_key"], unique=True)

    op.add_column(
        "scans",
        sa.Column(
            "org_id",
            uuid_type,
            sa.ForeignKey("organizations.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_scans_org_id", "scans", ["org_id"])


def downgrade() -> None:
    op.drop_index("ix_scans_org_id", table_name="scans")
    op.drop_column("scans", "org_id")
    op.drop_index("ix_api_keys_hashed_key", table_name="api_keys")
    op.drop_index("ix_api_keys_org_id", table_name="api_keys")
    op.drop_table("api_keys")
    op.drop_index("ix_org_memberships_user_id", table_name="org_memberships")
    op.drop_index("ix_org_memberships_org_id", table_name="org_memberships")
    op.drop_table("org_memberships")
    op.drop_index("ix_organizations_slug", table_name="organizations")
    op.drop_table("organizations")
