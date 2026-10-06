"""Paginated busca ativa read use case (participant detail "carregar mais")."""

from typing import Any

from src.pic.application.ports.busca_ativa_repository import (
    BuscaAtivaRepository,
)
from src.pic.domain.models.busca_ativa import BuscaAtivaEvento


class BuscaAtivaPage:
    """One page of busca ativa events plus pagination metadata."""

    def __init__(
        self,
        data: list[BuscaAtivaEvento],
        offset: int,
        limit: int,
        has_more: bool,
    ):
        self.data = data
        self.offset = offset
        self.limit = limit
        self.has_more = has_more


class GetBuscaAtivaEventsUseCase:
    """Fetch one page of a participant's busca ativa events (newest first).

    Fetches `limit + 1` rows to detect `has_more`. A data-proxy failure
    degrades to `None` (same best-effort contract as the detail's embedded
    busca ativa read).
    """

    def __init__(self, repository: BuscaAtivaRepository):
        self._repository = repository

    async def execute(
        self,
        id_membro_familia: str,
        *,
        offset: int = 0,
        limit: int = 20,
        user_token: str | None = None,
        permissions: Any = None,
    ) -> BuscaAtivaPage | None:
        fetched = await self._repository.get_busca_ativa(
            id_membro_familia=id_membro_familia,
            user_token=user_token,
            offset=offset,
            limit=limit + 1,
            permissions=permissions,
        )
        if fetched is None:
            return None

        has_more = len(fetched) > limit
        return BuscaAtivaPage(
            data=fetched[:limit],
            offset=offset,
            limit=limit,
            has_more=has_more,
        )
