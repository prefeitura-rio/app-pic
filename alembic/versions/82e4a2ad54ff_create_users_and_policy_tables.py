"""create users and policy tables

Revision ID: 82e4a2ad54ff
Revises:
Create Date: 2026-08-20 17:22:11.309252

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from src.config import env

# revision identifiers, used by Alembic.
revision: str = '82e4a2ad54ff'
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Table names come from APP_PIC_USERS_TABLE/APP_PIC_POLICY_TABLE (not
# hardcoded) so this exact migration creates users_staging/policy_staging or
# users_prod/policy_prod depending on which env is active when it runs — see
# alembic/env.py for how each environment tracks its own applied revisions.
USERS_TABLE = env.APP_PIC_USERS_TABLE
POLICY_TABLE = env.APP_PIC_POLICY_TABLE


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        USERS_TABLE,
        sa.Column('cpf', sa.String(), nullable=False),
        sa.Column('nome', sa.String(), nullable=True),
        sa.Column('email', sa.String(), nullable=True),
        sa.Column('ocupacao', sa.String(), nullable=True),
        sa.Column('secretaria', sa.String(), nullable=True),
        sa.Column('is_admin', sa.Boolean(), nullable=False),
        sa.Column('is_super_admin', sa.Boolean(), nullable=False),
        sa.Column('active', sa.Boolean(), nullable=False),
        sa.Column('notes', sa.String(), nullable=True),
        sa.Column('created_by', sa.String(), nullable=True),
        sa.Column('updated_by', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('cpf'),
    )
    op.create_table(
        POLICY_TABLE,
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('schema', sa.String(), nullable=False),
        sa.Column('subject', sa.String(), nullable=False),
        sa.Column('is_admin', sa.Boolean(), nullable=False),
        sa.Column('is_enabled', sa.Boolean(), nullable=False),
        sa.Column('unit_type', sa.String(), nullable=True),
        sa.Column('unit_id', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('synced_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['subject'], [f'{USERS_TABLE}.cpf']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'schema', 'subject', 'unit_type', 'unit_id', name=f'uq_{POLICY_TABLE}_grant'
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table(POLICY_TABLE)
    op.drop_table(USERS_TABLE)
