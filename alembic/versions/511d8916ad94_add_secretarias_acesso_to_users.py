"""add secretarias_acesso to users

Revision ID: 511d8916ad94
Revises: 82e4a2ad54ff
Create Date: 2026-08-20 17:42:34.239169

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '511d8916ad94'
down_revision: str | Sequence[str] | None = '82e4a2ad54ff'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema.

    Table name is fixed — environment isolation (staging/prod) is done via
    Postgres schema, applied at the connection level. Run once per
    environment, swapping APP_PIC_PG_SCHEMA in between.
    """
    op.add_column(
        "users",
        sa.Column(
            "secretarias_acesso",
            sa.ARRAY(sa.String()),
            server_default="{}",
            nullable=False,
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("users", "secretarias_acesso")
