from collections.abc import AsyncIterator
from typing import Any

from src.pic.application.ports.participant_read_repository import ParticipantRepository
from src.pic.domain.models.filters import FilterCriteria
from src.pic.domain.models.pagination import SortParams
from src.pic.infrastructure.repositories.postgrest_participant_repository import (
    EXPORT_FALLBACK_COLUMNS,
)


class ExportOutput:
    def __init__(
        self,
        columns: list[str],
        pages: AsyncIterator[list[dict[str, Any]]],
    ):
        self.columns = columns
        self.pages = pages


async def _empty_pages() -> AsyncIterator[list[dict[str, Any]]]:
    return
    yield  # pragma: no cover


class ExportParticipantsUseCase:
    def __init__(self, repository: ParticipantRepository):
        self._repository = repository

    async def execute(
        self,
        filters: FilterCriteria,
        sort: SortParams,
        permissions: Any = None,
        user_token: str | None = None,
        bypass_cache: bool = False,
    ) -> ExportOutput:
        """Prepare the CSV export stream.

        The first page is fetched eagerly so 403/422/502 errors and the
        column names are resolved *before* the HTTP response starts; the
        remaining pages stream lazily. `bypass_cache` is accepted for API
        compatibility (the export never reads the cache).
        """
        pages = self._repository.export_wide_rows(
            filters=filters,
            sort=sort,
            permissions=permissions,
            user_token=user_token,
        )

        try:
            first_page = await anext(pages)
        except StopAsyncIteration:
            return ExportOutput(columns=EXPORT_FALLBACK_COLUMNS, pages=_empty_pages())

        columns = list(first_page[0].keys()) if first_page else EXPORT_FALLBACK_COLUMNS

        async def _all_pages() -> AsyncIterator[list[dict[str, Any]]]:
            if first_page:
                yield first_page
            async for page in pages:
                yield page

        return ExportOutput(columns=columns, pages=_all_pages())
