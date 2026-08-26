"""policy unit_type unit_id not null with base sentinel

Revision ID: 52a8242e7e13
Revises: 511d8916ad94
Create Date: 2026-08-21 16:04:24.268571

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from src.config import env

# revision identifiers, used by Alembic.
revision: str = "52a8242e7e13"
down_revision: str | Sequence[str] | None = "511d8916ad94"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

POLICY_TABLE = "policy"

# Explicit schema, instead of relying on the connection's
# `schema_translate_map` (staging vs prod — see alembic/env.py and
# src/pic/infrastructure/db/engine.py) like every other migration in this
# repo does. Confirmed empirically that `schema_translate_map` only
# translates plain `sa.Table`-bound DML (SELECT/UPDATE/INSERT) — it's
# silently ignored by Alembic's own DDL operations (`op.alter_column`,
# which this migration needs), so those would otherwise run against
# whichever schema the connection's `search_path` defaults to (`public`),
# not the intended environment, and fail with `UndefinedTableError`.
SCHEMA = env.APP_PIC_PG_SCHEMA

# Sentinel used for the super_admin "base" row instead of NULL/NULL. Postgres
# treats NULL <> NULL in the unique constraint below, so two upsert attempts
# for the base row would insert two rows instead of merging into one — a
# fixed string sentinel doesn't have that problem. See plan.md section 3.2.
BASE_SENTINEL = "_base"


def upgrade() -> None:
    """Upgrade schema."""
    # Backfill: super_admin base rows created by
    # scripts/migrate_policy_bq_to_postgres.py (before this sentinel
    # convention existed) have unit_type/unit_id = NULL/NULL.
    policy = sa.Table(
        POLICY_TABLE,
        sa.MetaData(),
        sa.Column("unit_type", sa.String()),
        sa.Column("unit_id", sa.String()),
        schema=SCHEMA,
    )
    op.execute(
        policy.update()
        .where(policy.c.unit_type.is_(None))
        .values(unit_type=BASE_SENTINEL)
    )
    op.execute(
        policy.update().where(policy.c.unit_id.is_(None)).values(unit_id=BASE_SENTINEL)
    )

    op.alter_column(
        POLICY_TABLE,
        "unit_type",
        existing_type=sa.String(),
        nullable=False,
        schema=SCHEMA,
    )
    op.alter_column(
        POLICY_TABLE,
        "unit_id",
        existing_type=sa.String(),
        nullable=False,
        schema=SCHEMA,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.alter_column(
        POLICY_TABLE,
        "unit_type",
        existing_type=sa.String(),
        nullable=True,
        schema=SCHEMA,
    )
    op.alter_column(
        POLICY_TABLE, "unit_id", existing_type=sa.String(), nullable=True, schema=SCHEMA
    )
