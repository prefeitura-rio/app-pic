import pytest

from src.pic.application.use_cases.export_participants import (
    ExportParticipantsUseCase,
)
from src.pic.domain.errors import ForbiddenError
from src.pic.domain.models.filters import FilterCriteria
from src.pic.domain.models.pagination import SortParams
from src.pic.infrastructure.repositories.helpers.participant_columns import (
    EXPORT_FALLBACK_COLUMNS,
)


class FakeExportRepository:
    export_fallback_columns = EXPORT_FALLBACK_COLUMNS

    def __init__(self, pages: list[list[dict]]):
        self.pages = pages
        self.received: dict = {}

    def export_columns(self, permissions=None):
        return EXPORT_FALLBACK_COLUMNS

    async def export_wide_rows(self, filters, sort, permissions=None, user_token=None):
        self.received = {
            "filters": filters,
            "sort": sort,
            "permissions": permissions,
            "user_token": user_token,
        }
        for page in self.pages:
            yield page


@pytest.mark.asyncio
async def test_execute_columns_come_from_fixed_map_and_streams_all_pages():
    # First row carries a non-map column (`cpf_particao`) and only a subset of
    # the fixed columns — the header must still be the full fixed map, not the
    # keys of the first row.
    repo = FakeExportRepository(
        [
            [{"id_membro_familia": "1", "nome": "A", "cpf_particao": 7}],
            [{"id_membro_familia": "2", "nome": "B"}],
        ]
    )
    use_case = ExportParticipantsUseCase(repo)

    result = await use_case.execute(
        filters=FilterCriteria(status="Ativo"),
        sort=SortParams(sort_by="nome"),
        permissions=None,
        user_token="token",
    )

    assert result.columns == EXPORT_FALLBACK_COLUMNS
    assert "cpf_particao" not in result.columns
    rows = [row async for page in result.pages for row in page]
    assert [row["id_membro_familia"] for row in rows] == ["1", "2"]
    assert repo.received["user_token"] == "token"
    assert repo.received["filters"].status == "Ativo"


@pytest.mark.asyncio
async def test_execute_empty_export_falls_back_to_static_columns():
    use_case = ExportParticipantsUseCase(FakeExportRepository([]))

    result = await use_case.execute(
        filters=FilterCriteria(), sort=SortParams(), permissions=None
    )

    assert result.columns == EXPORT_FALLBACK_COLUMNS
    assert [row async for page in result.pages for row in page] == []


@pytest.mark.asyncio
async def test_execute_raises_repository_errors_eagerly():
    class FailingRepository:
        def export_columns(self, permissions=None):
            return EXPORT_FALLBACK_COLUMNS

        async def export_wide_rows(
            self, filters, sort, permissions=None, user_token=None
        ):
            raise ForbiddenError("Sem acesso")
            yield []  # pragma: no cover

    use_case = ExportParticipantsUseCase(FailingRepository())

    with pytest.raises(ForbiddenError):
        await use_case.execute(filters=FilterCriteria(), sort=SortParams())
