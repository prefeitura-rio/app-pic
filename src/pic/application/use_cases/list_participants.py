from typing import Any

from src.pic.application.ports.busca_ativa_repository import (
    BuscaAtivaRepository,
)
from src.pic.application.ports.participant_repository import (
    ParticipantRepository,
)
from src.pic.domain.models.filters import FilterCriteria
from src.pic.domain.models.pagination import (
    PaginationMeta,
    PaginationParams,
    SortParams,
)
from src.pic.domain.models.participante import ParticipanteListItem

# Cap on the enrichment query: beyond this many members per page the
# `id_membro_familia=in.(...)` URL gets too long. Download mode (-1) is
# never enriched.
MAX_MEMBERS_ENRICHMENT = 1000


class ParticipantListOutput:
    def __init__(
        self,
        data: list[ParticipanteListItem],
        meta: PaginationMeta,
    ):
        self.data = data
        self.meta = meta


class ListParticipantsUseCase:
    def __init__(
        self,
        repository: ParticipantRepository,
        busca_ativa_repository: BuscaAtivaRepository | None = None,
    ):
        self._repository = repository
        self._busca_ativa_repository = busca_ativa_repository

    async def execute(
        self,
        filters: FilterCriteria,
        pagination: PaginationParams,
        sort: SortParams,
        permissions: Any = None,
        bypass_cache: bool = False,
        user_token: str | None = None,
    ) -> ParticipantListOutput:
        data, meta = await self._repository.list_participants(
            filters=filters,
            pagination=pagination,
            sort=sort,
            permissions=permissions,
            user_token=user_token,
            bypass_cache=bypass_cache,
        )
        await self._enrich_busca_ativa(data, pagination, user_token, permissions)
        return ParticipantListOutput(data=data, meta=meta)

    async def _enrich_busca_ativa(
        self,
        data: list[ParticipanteListItem],
        pagination: PaginationParams,
        user_token: str | None,
        permissions: Any,
    ) -> None:
        """Flag which list rows have at least one busca ativa event.

        Best-effort: a data-proxy failure keeps `has_busca_ativa=None`
        (the column renders as "-"). Download mode is skipped entirely, and
        the recorte respects the same secretaria access as the detail.
        """
        if self._busca_ativa_repository is None or pagination.page_size == -1:
            return

        ids = [
            item.id_membro_familia
            for item in data
            if item.id_membro_familia is not None
        ]
        if not ids or len(ids) > MAX_MEMBERS_ENRICHMENT:
            return

        members = await self._busca_ativa_repository.get_members_with_busca_ativa(
            ids, user_token=user_token, permissions=permissions
        )
        if members is None:
            return

        for item in data:
            item.has_busca_ativa = item.id_membro_familia in members
