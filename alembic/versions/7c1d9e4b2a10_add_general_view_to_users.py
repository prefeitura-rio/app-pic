"""add general_view to users and move the base policy row to the wildcard grant

Revision ID: 7c1d9e4b2a10
Revises: 52a8242e7e13
Create Date: 2026-10-28 12:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "7c1d9e4b2a10"
down_revision: str | Sequence[str] | None = "52a8242e7e13"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema.

    Table names are fixed — environment isolation (staging/prod) is done via
    Postgres schema, applied at the connection level. Run once per
    environment, swapping APP_PIC_PG_SCHEMA in between.
    """
    op.add_column(
        "users",
        sa.Column(
            "general_view",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
    )
    op.execute(
        "UPDATE policy SET unit_type = '*', unit_id = '*', is_admin = false, "
        "synced_at = NULL WHERE unit_type = '_base' AND unit_id = '_base'"
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute(
        "UPDATE policy SET unit_type = '_base', unit_id = '_base', is_admin = true, "
        "synced_at = NULL WHERE unit_type = '*' AND unit_id = '*'"
    )
    op.drop_column("users", "general_view")
