"""add general_view to users and move the base policy row to the wildcard grant

Revision ID: 7c1d9e4b2a10
Revises: 52a8242e7e13
Create Date: 2026-10-28 12:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from src.config import env

revision: str = "7c1d9e4b2a10"
down_revision: str | Sequence[str] | None = "52a8242e7e13"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = env.APP_PIC_PG_SCHEMA


def upgrade() -> None:
    """Upgrade schema.

    Run once per environment, swapping APP_PIC_PG_SCHEMA in between. The
    schema is explicit because Alembic DDL ignores `schema_translate_map`.
    """
    op.add_column(
        "users",
        sa.Column(
            "general_view",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
        schema=SCHEMA,
    )
    op.execute(
        f"UPDATE {SCHEMA}.policy SET unit_type = '*', unit_id = '*', is_admin = false, "
        "synced_at = NULL WHERE unit_type = '_base' AND unit_id = '_base'"
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute(
        f"UPDATE {SCHEMA}.policy SET unit_type = '_base', unit_id = '_base', is_admin = true, "
        "synced_at = NULL WHERE unit_type = '*' AND unit_id = '*'"
    )
    op.drop_column("users", "general_view", schema=SCHEMA)
