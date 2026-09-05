from abc import ABC, abstractmethod
from typing import Any

import polars as pl

from src.core.security.permissions_models import IdWithName, UserPermissions


class IAdminRepository(ABC):
    @abstractmethod
    async def fetch_user_permissions(self, cpf: str) -> UserPermissions:
        """Hot-path lookup used on every authenticated request (via JWT).

        Must be fast (single indexed query) and must NOT resolve unit-id
        display names (no participants catalog join) - callers that need
        real names should go through `fetch_governance_df` instead.
        """
        ...

    @abstractmethod
    async def fetch_governance_df(self) -> tuple[pl.DataFrame, bool, Any]:
        """All users + enabled policy rows (RAW unit ids — no PostgREST).

        Unit ids double as display-name fallback; the UI resolves real names
        lazily from the per-type dropdown options.
        """
        ...

    @abstractmethod
    async def fetch_user_record(
        self, cpf: str, user_token: str | None = None
    ) -> dict[str, Any] | None:
        """One user's row from Postgres (RAW unit ids, no PostgREST)."""
        ...

    @abstractmethod
    async def fetch_unit_options(
        self,
        unit_type: str,
        user_token: str | None = None,
        bypass_cache: bool = False,
    ) -> list[IdWithName]:
        """Distinct id/nome pairs for one unit type (RLS-filtered per user)."""
        ...

    @abstractmethod
    async def find_paginated_users(
        self,
        filters_dict: dict[str, Any],
        page: int,
        page_size: int,
        search: str | None,
        filter_columns_config: dict[str, Any],
    ) -> tuple[pl.DataFrame, Any, Any]:
        ...

    @abstractmethod
    async def find_users_by_cpfs(self, cpfs: list[str]) -> pl.DataFrame:
        ...

    @abstractmethod
    async def update_user(
        self,
        cpf: str,
        fields: dict[str, Any],
        id_lists: dict[str, list[IdWithName] | None],
        updated_by: str,
    ) -> None:
        ...

    @abstractmethod
    async def insert_user(
        self,
        cpf: str,
        fields: dict[str, Any],
        id_lists: dict[str, list[IdWithName] | None],
        created_by: str,
    ) -> None:
        ...

    @abstractmethod
    async def soft_delete_user(self, cpf: str, updated_by: str) -> None:
        ...

    @abstractmethod
    async def batch_merge_permissions(
        self,
        valid_users: list[dict[str, Any]],
        is_admin: bool,
        permission: str,
        id_lists: dict[str, list[IdWithName] | None],
        secretarias_acesso: list[str] | None,
        updated_by: str,
    ) -> None:
        ...

    @abstractmethod
    async def self_heal_policy_sync(self, cpf: str, force: bool = False) -> None:
        """Retry pushing this subject's `policy` rows that are still pending
        sync to the data-proxy (eager push failed or was never attempted).

        Args:
            cpf: Subject CPF to sync policies for.
            force: If True, sync ALL policies regardless of synced_at status.
                   If False (default), only sync stale/pending policies.
                   Set to True on fresh login via ?force_sync=true query param.

        Best-effort and non-blocking: implementations must never raise.
        Called once per login from `GET /admin/me` as a safety net — see
        plan.md section 5.
        """
        ...
