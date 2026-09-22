"""ORM models for the app-pic Postgres.

Two tables, per plan.md sections 3.1/3.2:

- `users`: identity + app-only business flags (never sent to the data-proxy).
- `policy`: local mirror of data-proxy's `rls.access_policy`. Postgres local
  is the write of record (writes here always succeed independently of the
  data-proxy); `synced_at` tracks whether this row has been pushed to the
  data-proxy yet — see `AccessPolicySync` and plan.md section 5.
"""

from datetime import datetime

from sqlalchemy import (
    ARRAY,
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.pic.infrastructure.db.base import Base

# Sentinel for the subject's "base" row (identity/super_admin bypass row),
# used instead of NULL/NULL so the (schema, subject, unit_type, unit_id)
# unique constraint behaves correctly on upsert (Postgres treats NULL <> NULL
# in unique constraints, which would let two upsert attempts for the base row
# create two rows instead of merging into one). Only a local-table
# convention; the data-proxy's `rls.access_policy.unit_type`/`unit_id` stay
# nullable (shared table, outside our control) but we never write NULL into
# them either. See plan.md section 3.2.
BASE_UNIT_TYPE = "_base"
BASE_UNIT_ID = "_base"


class User(Base):
    # Table name is fixed — staging and prod share the same Postgres
    # instance/database, but isolation is by Postgres schema (see
    # `schema_translate_map` in engine.py), not by table name. See plan.md
    # section 7.
    __tablename__ = "users"

    cpf: Mapped[str] = mapped_column(String, primary_key=True)

    nome: Mapped[str | None] = mapped_column(String)
    email: Mapped[str | None] = mapped_column(String)
    ocupacao: Mapped[str | None] = mapped_column(String)
    secretaria: Mapped[str | None] = mapped_column(String)

    # Subset of {SME, SMS, SMAS} this subject can see `protocolo_listagem`
    # entries for. Never sent to the data-proxy: `secretaria` isn't a flat
    # column on the participant row (it's inside a nested array), so it can't
    # be enforced by native Postgres RLS — the app-pic backend filters the
    # array in Polars after the data-proxy returns unit-filtered rows. See
    # plan.md section 4. `{}` = no protocol access (replaces the old
    # None/"NULL"/absent trio); `{SME,SMS,SMAS}` = full access (replaces the
    # old "TODOS" magic value).
    secretarias_acesso: Mapped[list[str]] = mapped_column(
        ARRAY(String), nullable=False, default=list, server_default="{}"
    )

    # "Admin comum": manages a subset of users (own units' subset). Pure app
    # business rule, validated in the backend — never sent to the data-proxy.
    is_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Manages every user AND sees every row of data. Mirrors to `is_admin=true`
    # on this subject's base `policy` row (unit_type/unit_id NULL).
    is_super_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Soft delete for the whole account. Mirrors to a revoke (DELETE) of every
    # `policy` row for this subject on the data-proxy.
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    notes: Mapped[str | None] = mapped_column(String)

    created_by: Mapped[str | None] = mapped_column(String)
    updated_by: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    policies: Mapped[list["PolicyRow"]] = relationship(
        back_populates="user",
        primaryjoin="User.cpf == foreign(PolicyRow.subject)",
        viewonly=True,
    )


class PolicyRow(Base):
    """Local mirror of one row of data-proxy's `rls.access_policy`.

    Postgres local is the write of record — see plan.md section 5.
    `metadata` is intentionally not mirrored here; we never use it. Never
    hard-deleted locally (append-only): revoking a grant sets
    `is_enabled=false`, and `AccessPolicySync` translates that into a hard
    `DELETE` on the data-proxy, whose `access_policy` no longer has an
    `is_enabled` column (see plan.md section 3.3).
    """

    __tablename__ = "policy"
    __table_args__ = (
        UniqueConstraint(
            "schema",
            "subject",
            "unit_type",
            "unit_id",
            name="uq_policy_grant",
        ),
    )

    # `.with_variant(Integer, "sqlite")`: SQLite only auto-increments a
    # primary key declared as plain `INTEGER` (its rowid alias), not
    # `BIGINT` - this variant is a no-op on Postgres (still BIGINT there)
    # and only exists so an in-memory sqlite engine can be used in tests
    # (see repositories/tests/test_hybrid_admin.py) without a real Postgres.
    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True
    )

    schema: Mapped[str] = mapped_column(String, nullable=False)
    subject: Mapped[str] = mapped_column(String, ForeignKey(User.cpf), nullable=False)

    # True only on the super_admin's base row (unit_type/unit_id ==
    # BASE_UNIT_TYPE/BASE_UNIT_ID) — never combined with a specific unit. See
    # plan.md section 4.
    is_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Local soft-delete flag (the data-proxy's `access_policy` no longer has
    # this column): `false` means the sync must DELETE the corresponding row
    # there — see `AccessPolicySync`.
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # BASE_UNIT_TYPE/BASE_UNIT_ID = the subject's "base" row (identity/
    # super_admin bypass row). Otherwise one of: cras, escola, cre, ap, cas,
    # clinica_familia, equipe_familia, secretaria.
    unit_type: Mapped[str] = mapped_column(String, nullable=False)
    unit_id: Mapped[str] = mapped_column(String, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    # Timestamp of the last write confirmed on the data-proxy side for this
    # exact row. NULL, or older than `updated_at`, means this row is pending
    # sync — either the eager push after the local write failed (data-proxy
    # unavailable), or it hasn't been attempted yet. The login-time self-heal
    # (`GET /admin/me`) retries rows in this state. See plan.md section 5.
    synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped["User"] = relationship(
        back_populates="policies",
        primaryjoin="foreign(PolicyRow.subject) == User.cpf",
        viewonly=True,
    )
