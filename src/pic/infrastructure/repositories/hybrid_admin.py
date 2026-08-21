"""
Postgres-backed implementation of IAdminRepository, hybridized with a
best-effort mirror push to the data-proxy.

Replaces the old BigQuery `endpoint_data_access` table with two small
Postgres tables (`users`/`policy`, see `src.pic.infrastructure.db.models`).
Participants (used only to resolve real display names for unit IDs, and for
the super-admin "available ids" catalog) still come from BigQuery - that
domain is out of scope for this migration.

Scale note: this whole table pair has at most ~60 rows total, so unlike the
old BigQuery-backed repository there's no caching here at all - every read
goes straight to Postgres (a single indexed query, a few ms via Cloud SQL
Connector) and `fetch_governance_df`/`find_paginated_users` just load
everything into memory and filter/paginate in Polars.

Write order (plan.md section 5): Postgres local is always the write of
record — every write method below commits locally first, and only then
attempts a best-effort eager push of the rows that changed to the
data-proxy's `rls.access_policy` (`_push_eager`). A push failure is caught
and logged; it never fails the admin action, and never touches the local
`policy` rows again. `PolicyRow.synced_at` marks what's confirmed on the
data-proxy side; rows left with a stale/absent `synced_at` are retried by
the login-time self-heal (`GET /admin/me`, see
`src.pic.infrastructure.data_proxy.access_policy_sync.push_and_mark_synced`).
"""

from typing import Any

import polars as pl
from sqlalchemy import or_, select, update

from src.api.v1.queries import PARTICIPANTS_TABLE_QUERY
from src.config import env
from src.core.security.permissions_models import (
    IdWithName,
    PermissionDeniedError,
    UserPermissions,
)
from src.pic.application.ports.admin_repository import IAdminRepository
from src.pic.infrastructure.admin.id_utils import build_name_catalog
from src.pic.infrastructure.admin.validation import calculate_permission
from src.pic.infrastructure.data_proxy.access_policy_sync import push_and_mark_synced
from src.pic.infrastructure.db.engine import get_session
from src.pic.infrastructure.db.models import (
    BASE_UNIT_ID,
    BASE_UNIT_TYPE,
    PolicyRow,
    User,
)
from src.utils.data_manager import DataManager
from src.utils.log import logger

SCHEMA = env.DATA_PROXY_SCHEMA

# unit_type (policy) -> id_lists/domain key (admin.py)
UNIT_TYPE_TO_LIST_KEY: dict[str, str] = {
    "cras": "id_cras_list",
    "escola": "id_escola_list",
    "cre": "id_cre_list",
    "ap": "id_ap_list",
    "cas": "id_cas_list",
    "clinica_familia": "id_clinica_familia_list",
    "equipe_familia": "id_equipe_familia_list",
}
LIST_KEY_TO_UNIT_TYPE: dict[str, str] = {v: k for k, v in UNIT_TYPE_TO_LIST_KEY.items()}


class HybridAdminRepository(IAdminRepository):
    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    async def fetch_user_permissions(self, cpf: str) -> UserPermissions:
        async with get_session() as session:
            user_result = await session.execute(select(User).where(User.cpf == cpf))
            user = user_result.scalar_one_or_none()

            if user is None:
                raise PermissionDeniedError(
                    f"CPF {cpf} não cadastrado na base de acessos"
                )

            if not user.active:
                raise PermissionDeniedError(f"Usuário {cpf} está inativo")

            policy_result = await session.execute(
                select(PolicyRow.unit_type, PolicyRow.unit_id).where(
                    PolicyRow.schema == SCHEMA,
                    PolicyRow.subject == cpf,
                    PolicyRow.is_enabled.is_(True),
                    PolicyRow.unit_type != BASE_UNIT_TYPE,
                )
            )
            ids_by_unit_type: dict[str, list[str]] = {}
            for unit_type, unit_id in policy_result.all():
                ids_by_unit_type.setdefault(unit_type, []).append(unit_id)

        # Hot path: no participants catalog join, id doubles as display name.
        id_lists = {
            list_key: [
                IdWithName(id=i, nome=i) for i in ids_by_unit_type.get(unit_type, [])
            ]
            for unit_type, list_key in UNIT_TYPE_TO_LIST_KEY.items()
        }

        return UserPermissions(
            cpf=user.cpf,
            email=user.email,
            is_admin=user.is_admin,
            is_super_admin=user.is_super_admin,
            permission=calculate_permission(user.is_admin, user.is_super_admin),
            secretarias_acesso=list(user.secretarias_acesso or []),
            active=user.active,
            notes=user.notes,
            **id_lists,
        )

    async def fetch_participants_df(
        self, bypass_cache: bool = False
    ) -> tuple[pl.DataFrame, bool, Any]:
        return await DataManager.get_dataset(
            PARTICIPANTS_TABLE_QUERY, bypass_cache=bypass_cache
        )

    async def fetch_governance_df(
        self, bypass_cache: bool = False
    ) -> tuple[pl.DataFrame, bool, Any]:
        async with get_session() as session:
            users_result = await session.execute(select(User))
            users = users_result.scalars().all()

            policy_result = await session.execute(
                select(PolicyRow.subject, PolicyRow.unit_type, PolicyRow.unit_id).where(
                    PolicyRow.schema == SCHEMA,
                    PolicyRow.is_enabled.is_(True),
                    PolicyRow.unit_type != BASE_UNIT_TYPE,
                )
            )
            ids_by_subject: dict[str, dict[str, list[str]]] = {}
            for subject, unit_type, unit_id in policy_result.all():
                ids_by_subject.setdefault(subject, {}).setdefault(unit_type, []).append(
                    unit_id
                )

        participants_df, _, _ = await self.fetch_participants_df(
            bypass_cache=bypass_cache
        )
        name_catalog = build_name_catalog(participants_df)

        rows: list[dict[str, Any]] = []
        for user in users:
            user_ids = ids_by_subject.get(user.cpf, {})
            row: dict[str, Any] = {
                "cpf": user.cpf,
                "email": user.email,
                "nome": user.nome,
                "ocupacao": user.ocupacao,
                "secretaria": user.secretaria,
                "is_admin": user.is_admin,
                "is_super_admin": user.is_super_admin,
                "permission": calculate_permission(user.is_admin, user.is_super_admin),
                "secretarias_acesso": list(user.secretarias_acesso or []),
                "active": user.active,
                "notes": user.notes,
                "created_by": user.created_by,
                "created_at": user.created_at,
                "updated_by": user.updated_by,
                "updated_at": user.updated_at,
            }
            for unit_type, list_key in UNIT_TYPE_TO_LIST_KEY.items():
                ids = user_ids.get(unit_type, [])
                # build_name_catalog keys by the participants-df id column
                # name (e.g. "id_cras"), not the bare policy unit_type.
                catalog = name_catalog.get(f"id_{unit_type}", {})
                row[list_key] = [{"id": i, "nome": catalog.get(i, i)} for i in ids]
            rows.append(row)

        df = pl.DataFrame(rows) if rows else pl.DataFrame()
        return df, False, None

    async def find_paginated_users(
        self,
        filters_dict: dict[str, Any],
        page: int,
        page_size: int,
        search: str | None,
        filter_columns_config: dict[str, Any],
        bypass_cache: bool,
    ) -> tuple[pl.DataFrame, Any, Any]:
        from math import ceil

        from src.api.v1.schemas import PaginationMeta

        df, _, _ = await self.fetch_governance_df(bypass_cache=bypass_cache)

        # secretarias_acesso is a list[str] column - filter separately
        # ("contains any of the requested secretarias").
        secretarias_filter = filters_dict.pop("secretarias_acesso", None)

        df_filtered = (
            DataManager.apply_filters(df, filters_dict) if not df.is_empty() else df
        )

        if secretarias_filter and not df_filtered.is_empty():
            wanted = (
                secretarias_filter
                if isinstance(secretarias_filter, list)
                else [secretarias_filter]
            )
            df_filtered = df_filtered.filter(
                pl.col("secretarias_acesso")
                .list.eval(pl.element().is_in(wanted))
                .list.any()
            )

        if search and not df_filtered.is_empty():
            df_filtered = DataManager.apply_search(df_filtered, search, ["cpf", "nome"])

        filter_options = None
        if filter_columns_config and not df.is_empty():
            filter_options = DataManager.calculate_filter_options_fast(
                df_original=df,
                df_already_filtered=df_filtered,
                filter_columns_config=filter_columns_config,
                active_filters=filters_dict,
            )

        total_rows = len(df_filtered)
        if page_size is None or page_size == -1:
            total_pages = 1
            df_result = df_filtered
        else:
            total_pages = ceil(total_rows / page_size) if total_rows > 0 else 0
            df_result = df_filtered.slice((page - 1) * page_size, page_size)

        meta = PaginationMeta(
            page=page,
            page_size=page_size if page_size != -1 else None,
            total_rows=total_rows,
            total_pages=total_pages,
            cache_hit=False,
            profiling=None,
        )

        return df_result, meta, filter_options

    async def find_users_by_cpfs(self, cpfs: list[str]) -> pl.DataFrame:
        async with get_session() as session:
            result = await session.execute(
                select(User.cpf, User.is_admin, User.is_super_admin).where(
                    User.cpf.in_(cpfs)
                )
            )
            rows = [dict(r) for r in result.mappings().all()]
        return (
            pl.DataFrame(rows)
            if rows
            else pl.DataFrame(
                schema={
                    "cpf": pl.Utf8,
                    "is_admin": pl.Boolean,
                    "is_super_admin": pl.Boolean,
                }
            )
        )

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------

    @staticmethod
    def _user_fields(fields: dict[str, Any]) -> dict[str, Any]:
        """Keep only keys that are real columns on `User` (drop derived
        fields like `permission`, which isn't stored)."""
        allowed = {
            "email",
            "nome",
            "ocupacao",
            "secretaria",
            "secretarias_acesso",
            "is_admin",
            "is_super_admin",
            "active",
            "notes",
        }
        return {k: v for k, v in fields.items() if k in allowed}

    @staticmethod
    async def _replace_policy_grants(
        session,
        cpf: str,
        id_lists: dict[str, list[IdWithName] | None],
        is_enabled: bool,
    ) -> list[PolicyRow]:
        """Upsert grants for every provided unit_type list and soft-disable
        (never delete) previously granted units that dropped out of the
        list. Returns every `PolicyRow` that changed, so the caller can push
        them eagerly to the data-proxy afterwards.

        Never hard-deletes: `policy` mirrors `rls.access_policy`, which is
        append-only (the `policy_writer_<schema>` role has no DELETE grant
        there) — see plan.md section 3.2.
        """
        changed: list[PolicyRow] = []
        for list_key, unit_type in LIST_KEY_TO_UNIT_TYPE.items():
            id_list = id_lists.get(list_key)
            if id_list is None:
                continue  # not provided -> leave existing grants for this unit_type untouched

            existing_result = await session.execute(
                select(PolicyRow).where(
                    PolicyRow.schema == SCHEMA,
                    PolicyRow.subject == cpf,
                    PolicyRow.unit_type == unit_type,
                )
            )
            existing_by_unit_id = {
                row.unit_id: row for row in existing_result.scalars().all()
            }
            # Dedupe by id (keeps the last occurrence) — the incoming list
            # may contain repeated ids (e.g. frontend multi-select quirks),
            # and inserting the same brand-new (schema, subject, unit_type,
            # unit_id) twice in one flush violates `uq_policy_grant` before
            # the loop below ever gets a chance to see the first insert.
            wanted_items = {item.id: item for item in id_list}

            for unit_id, row in existing_by_unit_id.items():
                if unit_id not in wanted_items and row.is_enabled:
                    row.is_enabled = False
                    row.synced_at = None
                    changed.append(row)

            for item in wanted_items.values():
                row = existing_by_unit_id.get(item.id)
                if row is None:
                    row = PolicyRow(
                        schema=SCHEMA,
                        subject=cpf,
                        is_admin=False,
                        is_enabled=is_enabled,
                        unit_type=unit_type,
                        unit_id=item.id,
                        synced_at=None,
                    )
                    session.add(row)
                    changed.append(row)
                elif row.is_enabled != is_enabled:
                    row.is_enabled = is_enabled
                    row.synced_at = None
                    changed.append(row)
        return changed

    @staticmethod
    async def _set_all_policy_enabled(
        session, cpf: str, enabled: bool
    ) -> list[PolicyRow]:
        """Flip `is_enabled` on every `policy` row for this subject (used
        when `users.active` toggles — see plan.md section 4). Returns only
        the rows that actually changed."""
        result = await session.execute(
            select(PolicyRow).where(
                PolicyRow.schema == SCHEMA, PolicyRow.subject == cpf
            )
        )
        changed = []
        for row in result.scalars().all():
            if row.is_enabled != enabled:
                row.is_enabled = enabled
                row.synced_at = None
                changed.append(row)
        return changed

    @staticmethod
    async def _sync_super_admin_base_row(
        session, cpf: str, is_super_admin: bool, active: bool
    ) -> PolicyRow | None:
        """Create, re-enable, or disable the sentinel "base" row
        (`unit_type=unit_id=BASE_UNIT_TYPE`, `is_admin=true`) that grants
        data-proxy RLS bypass for a super_admin. The row is only enabled
        when the subject is both a super_admin and active — a request that
        sets `is_super_admin=True` and `active=False` at the same time
        (both fields live on the same edit form) must never leave the
        bypass row enabled. Returns the row if it changed, else None. See
        plan.md section 4."""
        enabled = is_super_admin and active
        result = await session.execute(
            select(PolicyRow).where(
                PolicyRow.schema == SCHEMA,
                PolicyRow.subject == cpf,
                PolicyRow.unit_type == BASE_UNIT_TYPE,
                PolicyRow.unit_id == BASE_UNIT_ID,
            )
        )
        row = result.scalar_one_or_none()

        if row is None:
            if not is_super_admin:
                return None
            row = PolicyRow(
                schema=SCHEMA,
                subject=cpf,
                is_admin=True,
                is_enabled=enabled,
                unit_type=BASE_UNIT_TYPE,
                unit_id=BASE_UNIT_ID,
                synced_at=None,
            )
            session.add(row)
            return row

        if row.is_enabled != enabled:
            row.is_enabled = enabled
            row.synced_at = None
            return row
        return None

    @staticmethod
    async def _push_eager(rows: list[PolicyRow]) -> None:
        """Best-effort push of freshly-committed `policy` rows to the
        data-proxy. Never raises and never blocks the admin action on
        failure — see plan.md section 5."""
        try:
            await push_and_mark_synced(rows)
        except Exception:
            logger.exception("Push eager para rls.access_policy falhou inesperadamente")

    async def update_user(
        self,
        cpf: str,
        fields: dict[str, Any],
        id_lists: dict[str, list[IdWithName] | None],
        updated_by: str,
    ) -> None:
        user_fields = self._user_fields(fields)
        user_fields["updated_by"] = updated_by

        changed: list[PolicyRow] = []
        async with get_session() as session:
            previous_active = None
            if "active" in user_fields:
                previous_active = await session.scalar(
                    select(User.active).where(User.cpf == cpf)
                )

            if user_fields:
                await session.execute(
                    update(User).where(User.cpf == cpf).values(**user_fields)
                )

            is_enabled = bool(user_fields.get("active", True))
            changed += await self._replace_policy_grants(
                session, cpf, id_lists, is_enabled
            )

            # Only mass-toggle every grant when `active` is genuinely
            # transitioning (e.g. suspend/reactivate the whole account) —
            # `fields["active"]` is unconditionally sent on every edit (see
            # `admin_write.py`), so comparing against the value already in
            # `users.active` avoids running this on every unrelated edit,
            # which would otherwise immediately re-enable units that
            # `_replace_policy_grants` just soft-disabled above (same
            # `changed` batch), pushing the same row twice to the data-proxy
            # in one upsert and crashing it with "ON CONFLICT DO UPDATE
            # command cannot affect row a second time".
            if (
                "active" in user_fields
                and previous_active is not None
                and previous_active != user_fields["active"]
            ):
                changed += await self._set_all_policy_enabled(
                    session, cpf, user_fields["active"]
                )

            if "is_super_admin" in user_fields:
                base_row = await self._sync_super_admin_base_row(
                    session, cpf, user_fields["is_super_admin"], active=is_enabled
                )
                if base_row is not None:
                    changed.append(base_row)

            await session.commit()
        logger.info(f"Usuario {cpf} atualizado (Postgres)")
        await self._push_eager(changed)

    async def insert_user(
        self,
        cpf: str,
        fields: dict[str, Any],
        id_lists: dict[str, list[IdWithName] | None],
        created_by: str,
    ) -> None:
        user_fields = self._user_fields(fields)
        user_fields.setdefault("active", True)
        user_fields.setdefault("is_admin", False)
        user_fields.setdefault("is_super_admin", False)
        user_fields.setdefault("secretarias_acesso", [])

        changed: list[PolicyRow] = []
        async with get_session() as session:
            session.add(
                User(
                    cpf=cpf, created_by=created_by, updated_by=created_by, **user_fields
                )
            )
            await session.flush()

            changed += await self._replace_policy_grants(
                session, cpf, id_lists, is_enabled=user_fields["active"]
            )

            if user_fields["is_super_admin"]:
                base_row = await self._sync_super_admin_base_row(
                    session, cpf, is_super_admin=True, active=user_fields["active"]
                )
                if base_row is not None:
                    changed.append(base_row)

            await session.commit()
        logger.info(f"Usuario {cpf} criado (Postgres)")
        await self._push_eager(changed)

    async def soft_delete_user(self, cpf: str, updated_by: str) -> None:
        async with get_session() as session:
            await session.execute(
                update(User)
                .where(User.cpf == cpf)
                .values(active=False, updated_by=updated_by)
            )
            changed = await self._set_all_policy_enabled(session, cpf, enabled=False)
            await session.commit()
        logger.info(f"Usuario {cpf} marcado como inativo (Postgres)")
        await self._push_eager(changed)

    async def batch_merge_permissions(
        self,
        valid_users: list[dict[str, Any]],
        is_admin: bool,
        permission: str,
        id_lists: dict[str, list[IdWithName] | None],
        secretarias_acesso: list[str] | None,
        updated_by: str,
    ) -> None:
        changed: list[PolicyRow] = []
        async with get_session() as session:
            existing_result = await session.execute(
                select(User.cpf).where(User.cpf.in_([u["cpf"] for u in valid_users]))
            )
            existing_cpfs = {r[0] for r in existing_result.all()}

            for user_data in valid_users:
                cpf = user_data["cpf"]
                common_fields: dict[str, Any] = {"is_admin": is_admin}
                if secretarias_acesso is not None:
                    common_fields["secretarias_acesso"] = secretarias_acesso

                if cpf in existing_cpfs:
                    await session.execute(
                        update(User)
                        .where(User.cpf == cpf)
                        .values(updated_by=updated_by, **common_fields)
                    )
                else:
                    session.add(
                        User(
                            cpf=cpf,
                            nome=user_data.get("nome"),
                            email=user_data.get("email"),
                            ocupacao=user_data.get("ocupacao"),
                            secretaria=user_data.get("secretaria"),
                            is_super_admin=False,
                            active=True,
                            created_by=updated_by,
                            updated_by=updated_by,
                            **common_fields,
                        )
                    )
                    await session.flush()

                # batch merge never touches is_super_admin (see common_fields
                # above), so there's no base row to sync here.
                changed += await self._replace_policy_grants(
                    session, cpf, id_lists, is_enabled=True
                )

            await session.commit()
        logger.info(f"Batch de {len(valid_users)} usuarios mesclado (Postgres)")
        await self._push_eager(changed)

    async def refresh_cache(self) -> None:
        # No cache in this repository - Postgres reads are already cheap
        # given the small table sizes (~60 users).
        pass

    async def self_heal_policy_sync(self, cpf: str) -> None:
        async with get_session() as session:
            result = await session.execute(
                select(PolicyRow).where(
                    PolicyRow.schema == SCHEMA,
                    PolicyRow.subject == cpf,
                    or_(
                        PolicyRow.synced_at.is_(None),
                        PolicyRow.synced_at < PolicyRow.updated_at,
                    ),
                )
            )
            pending = list(result.scalars().all())
        await self._push_eager(pending)
