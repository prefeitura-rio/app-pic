"""Tests for `ListParticipantsUseCase` (delegation to the repository)."""

import pytest

from src.pic.application.use_cases.list_participants import (
    ListParticipantsUseCase,
)
from src.pic.domain.models.filters import FilterCriteria
from src.pic.domain.models.pagination import (
    PaginationMeta,
    PaginationParams,
    SortParams,
)
from src.pic.domain.models.participante import ParticipanteListItem


def make_item(id_membro_familia: str) -> ParticipanteListItem:
    return ParticipanteListItem(id_membro_familia=id_membro_familia)


def make_meta() -> PaginationMeta:
    return PaginationMeta(
        page=1,
        page_size=50,
        total_rows=2,
        total_pages=1,
        cache_hit=False,
        profiling={},
        can_view_dashboard=None,
    )


class FakeParticipantRepository:
    def __init__(self, items=None, error=None):
        self._items = items if items is not None else []
        self._error = error
        self.received: dict = {}

    async def list_participants(
        self,
        filters,
        pagination,
        sort,
        permissions=None,
        user_token=None,
        bypass_cache=False,
    ):
        self.received = {
            "filters": filters,
            "pagination": pagination,
            "sort": sort,
            "permissions": permissions,
            "user_token": user_token,
            "bypass_cache": bypass_cache,
        }
        if self._error:
            raise self._error
        return self._items, make_meta()


@pytest.mark.asyncio
async def test_execute_delegates_and_returns_items():
    repo = FakeParticipantRepository([make_item("111"), make_item("222")])
    use_case = ListParticipantsUseCase(repository=repo)

    result = await use_case.execute(
        filters=FilterCriteria(status="Ativo"),
        pagination=PaginationParams(page=1, page_size=50),
        sort=SortParams(sort_by="nome"),
        permissions="perms",
        user_token="user-jwt",
        bypass_cache=True,
    )

    assert [item.id_membro_familia for item in result.data] == ["111", "222"]
    assert repo.received["filters"].status == "Ativo"
    assert repo.received["permissions"] == "perms"
    assert repo.received["user_token"] == "user-jwt"
    assert repo.received["bypass_cache"] is True


@pytest.mark.asyncio
async def test_execute_returns_empty_when_no_items():
    use_case = ListParticipantsUseCase(repository=FakeParticipantRepository([]))
    result = await use_case.execute(
        filters=FilterCriteria(),
        pagination=PaginationParams(),
        sort=SortParams(),
    )
    assert result.data == []
