"""Read-side participant repository port (list + detail + filter options).

Split from `IParticipantRepository` (which keeps the BigQuery-backed CSV
export) so the PostgREST-migrated operations have a narrow port they fully
own. Implemented by
`src.pic.infrastructure.repositories.postgrest_participant_repository`.
"""

from abc import ABC, abstractmethod
from typing import Any

from src.pic.domain.models.filters import FilterCriteria, FilterOption
from src.pic.domain.models.pagination import (
    PaginationMeta,
    PaginationParams,
    SortParams,
)
from src.pic.domain.models.participante import Participante, ParticipanteListItem


class ParticipantRepository(ABC):
    """Read-only access to participant list/detail/options via PostgREST.

    `user_token` is the authenticated end user's JWT, forwarded so PostgREST
    applies row-level security for that user; `permissions` drives the
    app-side secretaria governance that RLS does not cover.
    """

    @abstractmethod
    async def list_participants(
        self,
        filters: FilterCriteria,
        pagination: PaginationParams,
        sort: SortParams,
        permissions: Any = None,
        user_token: str | None = None,
        bypass_cache: bool = False,
    ) -> tuple[list[ParticipanteListItem], PaginationMeta]:
        """Return the paginated summary rows and the meta envelope."""

    @abstractmethod
    async def get_participant_by_id(
        self,
        id_membro_familia: str,
        permissions: Any = None,
        user_token: str | None = None,
    ) -> Participante | None:
        """Return the full participant row, or `None` when not found/visible."""

    @abstractmethod
    async def get_filter_options(
        self,
        field: str,
        filters: FilterCriteria,
        permissions: Any = None,
        user_token: str | None = None,
        bypass_cache: bool = False,
    ) -> list[FilterOption]:
        """Return the distinct options of one filter field for the active filters."""
