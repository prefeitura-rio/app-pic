"""Tests for `ListParticipantsUseCase` (list + busca ativa enrichment)."""

import pytest

from src.core.security.permissions_models import UserPermissions
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
            "pagination": pagination,
            "user_token": user_token,
        }
        if self._error:
            raise self._error
        return self._items, make_meta()


class FakeBuscaAtivaRepository:
    def __init__(self, members=None):
        self._members = members
        self.received: dict = {}

    async def get_members_with_busca_ativa(
        self, id_membros_familia, *, user_token=None, permissions=None
    ):
        self.received = {
            "ids": id_membros_familia,
            "user_token": user_token,
            "permissions": permissions,
        }
        return self._members


@pytest.mark.asyncio
async def test_execute_flags_members_with_busca_ativa():
    participant_repo = FakeParticipantRepository(
        [make_item("111"), make_item("222")]
    )
    busca_repo = FakeBuscaAtivaRepository({"222"})
    use_case = ListParticipantsUseCase(
        repository=participant_repo,
        busca_ativa_repository=busca_repo,
    )

    result = await use_case.execute(
        filters=FilterCriteria(),
        pagination=PaginationParams(),
        sort=SortParams(),
        user_token="user-jwt",
    )

    assert [item.has_busca_ativa for item in result.data] == [False, True]
    assert busca_repo.received["ids"] == ["111", "222"]
    assert busca_repo.received["user_token"] == "user-jwt"


@pytest.mark.asyncio
async def test_execute_forwards_permissions_to_busca_ativa():
    permissions = UserPermissions(
        cpf="11111111111", is_admin=False, is_super_admin=False,
        secretarias_acesso=["SMS"],
    )
    use_case = ListParticipantsUseCase(
        repository=FakeParticipantRepository([make_item("111")]),
        busca_ativa_repository=FakeBuscaAtivaRepository(set()),
    )

    await use_case.execute(
        filters=FilterCriteria(),
        pagination=PaginationParams(),
        sort=SortParams(),
        permissions=permissions,
    )

    assert use_case._busca_ativa_repository.received["permissions"] is permissions


@pytest.mark.asyncio
async def test_execute_busca_ativa_none_keeps_field_none():
    use_case = ListParticipantsUseCase(
        repository=FakeParticipantRepository([make_item("111")]),
        busca_ativa_repository=FakeBuscaAtivaRepository(None),
    )

    result = await use_case.execute(
        filters=FilterCriteria(),
        pagination=PaginationParams(),
        sort=SortParams(),
    )

    assert result.data[0].has_busca_ativa is None


@pytest.mark.asyncio
async def test_execute_skips_enrichment_in_download_mode():
    participant_repo = FakeParticipantRepository([make_item("111")])
    busca_repo = FakeBuscaAtivaRepository({"111"})
    use_case = ListParticipantsUseCase(
        repository=participant_repo,
        busca_ativa_repository=busca_repo,
    )

    result = await use_case.execute(
        filters=FilterCriteria(),
        pagination=PaginationParams(page_size=-1),
        sort=SortParams(),
    )

    assert result.data[0].has_busca_ativa is None
    assert busca_repo.received == {}


@pytest.mark.asyncio
async def test_execute_without_busca_ativa_repository_keeps_field_none():
    use_case = ListParticipantsUseCase(
        repository=FakeParticipantRepository([make_item("111")]),
    )

    result = await use_case.execute(
        filters=FilterCriteria(),
        pagination=PaginationParams(),
        sort=SortParams(),
    )

    assert result.data[0].has_busca_ativa is None
