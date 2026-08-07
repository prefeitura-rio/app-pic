from abc import ABC, abstractmethod
from typing import Any

import polars as pl

from src.core.security.permissions_models import IdWithName


class IAdminRepository(ABC):
    @abstractmethod
    async def fetch_governance_df(self, bypass_cache: bool = False) -> pl.DataFrame:
        ...

    @abstractmethod
    async def fetch_participants_df(self, bypass_cache: bool = False) -> pl.DataFrame:
        ...

    @abstractmethod
    async def find_paginated_users(
        self,
        filters_dict: dict[str, Any],
        page: int,
        page_size: int,
        search: str | None,
        filter_columns_config: dict[str, Any],
        bypass_cache: bool,
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
        secretaria_acesso: str | None,
        updated_by: str,
    ) -> None:
        ...

    @abstractmethod
    async def refresh_cache(self) -> None:
        ...
