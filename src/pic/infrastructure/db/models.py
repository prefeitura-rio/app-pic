"""ORM models for the app-pic Postgres.

Two tables, per plan.md sections 3.1/3.2:

- `users`: identity + app-only business flags (never sent to the data-proxy).
- `policy`: local mirror of data-proxy's `rls.access_policy`, written only
  after a write is confirmed on the data-proxy side (data-proxy is the gate;
  this table just reflects what's already true there for fast local reads).
"""

from datetime import datetime

from sqlalchemy import (
    ARRAY,
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.config import env
from src.pic.infrastructure.db.base import Base


class User(Base):
    # Table name is env-driven (users_staging/users_prod) — staging and prod
    # share the same Postgres instance/database, so isolation is by table
    # name rather than by separate database/schema. See plan.md section 7.
    __tablename__ = env.APP_PIC_USERS_TABLE

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
    # Soft delete for the whole account. Mirrors to `is_enabled=false` on every
    # `policy` row for this subject.
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

    Only written after the equivalent PATCH/POST succeeds against the
    data-proxy — see plan.md section 5. `metadata` is intentionally not
    mirrored here; we never use it.
    """

    __tablename__ = env.APP_PIC_POLICY_TABLE
    __table_args__ = (
        # Constraint name includes the table name: unique/index names are
        # namespaced per schema in Postgres, not per table, and staging/prod
        # tables live in the same schema — a fixed name would collide once
        # both `policy_staging` and `policy_prod` exist.
        UniqueConstraint(
            "schema",
            "subject",
            "unit_type",
            "unit_id",
            name=f"uq_{env.APP_PIC_POLICY_TABLE}_grant",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    schema: Mapped[str] = mapped_column(String, nullable=False)
    subject: Mapped[str] = mapped_column(String, ForeignKey(User.cpf), nullable=False)

    # True only on the super_admin's base row (unit_type/unit_id NULL) —
    # never combined with a specific unit. See plan.md section 4.
    is_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # NULL/NULL = the subject's "base" row (identity/super_admin bypass row).
    # Otherwise one of: cras, escola, cre, ap, cas, clinica_familia,
    # equipe_familia, secretaria.
    unit_type: Mapped[str | None] = mapped_column(String)
    unit_id: Mapped[str | None] = mapped_column(String)

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
    # exact row. NULL means this row was never successfully synced (shouldn't
    # happen given the write order in plan.md section 5, but useful as a
    # canary for manual/out-of-band drift).
    synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped["User"] = relationship(
        back_populates="policies",
        primaryjoin="foreign(PolicyRow.subject) == User.cpf",
        viewonly=True,
    )
