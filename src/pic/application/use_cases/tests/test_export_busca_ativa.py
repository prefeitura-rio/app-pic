from datetime import date

import pytest

from src.core.security.permissions_models import UserPermissions
from src.pic.application.use_cases.export_busca_ativa import (
    ExportBuscaAtivaUseCase,
)
from src.pic.domain.errors import ForbiddenError
from src.pic.domain.models.busca_ativa import (
    BuscaAtivaEvento,
    BuscaAtivaUnidadeReferenciada,
    BuscaAtivaUnidadeSMAS,
    BuscaAtivaUnidadeSMS,
)
from src.pic.domain.models.filters import FilterCriteria
from src.pic.domain.models.pagination import SortParams
from src.pic.infrastructure.export.busca_ativa_columns import (
    build_busca_ativa_header,
)


class FakeParticipantRepo:
    def __init__(self, pages):
        self.pages = pages
        self.received: dict = {}

    async def export_busca_ativa_rows(
        self, filters, sort, permissions=None, user_token=None
    ):
        self.received = {
            "filters": filters,
            "sort": sort,
            "permissions": permissions,
            "user_token": user_token,
        }
        for page in self.pages:
            yield page


class FakeBuscaAtivaRepo:
    def __init__(self, eventos):
        self.eventos = eventos  # list[(member_id, evento)]
        self.received: dict = {}

    async def get_busca_ativa_for_members(
        self, ids, user_token=None, permissions=None, fontes=None
    ):
        self.received = {"ids": ids, "user_token": user_token, "fontes": fontes}
        wanted = set(ids)
        return [(member_id, e) for member_id, e in self.eventos if member_id in wanted]


def _evento(fonte="SMAS", data=date(2026, 7, 14), unidade_smas="CRAS X"):
    return BuscaAtivaEvento(
        id_busca_ativa="abc",
        fonte=fonte,
        data=data,
        smas_tipo=["Por telefone"],
        unidade_referenciada=BuscaAtivaUnidadeReferenciada(
            sms=None,
            smas=BuscaAtivaUnidadeSMAS(nome=unidade_smas, regional="AP 3.3"),
        ),
    )


def _page(member_id):
    return {
        "id_membro_familia": member_id,
        "cpf": f"cpf-{member_id}",
        "nome": f"Nome {member_id}",
        "nascimento_data": "2020-01-01",
        "endereco": "Rua A",
        "complemento": None,
        "bairro": "Centro",
        "endereco_sms": None,
    }


@pytest.mark.asyncio
async def test_execute_streams_event_rows_in_participant_then_newest_first_order():
    participant_repo = FakeParticipantRepo(
        [
            [_page("1"), _page("2")],
        ]
    )
    busca_ativa_repo = FakeBuscaAtivaRepo(
        [
            ("1", _evento(data=date(2026, 7, 14), unidade_smas="CRAS A")),
            ("1", _evento(data=date(2026, 6, 1), unidade_smas="CRAS B")),
            ("2", _evento(fonte="SMS", data=date(2026, 7, 10), unidade_smas=None)),
        ]
    )
    use_case = ExportBuscaAtivaUseCase(participant_repo, busca_ativa_repo)

    result = await use_case.execute(
        filters=FilterCriteria(),
        sort=SortParams(sort_by="nome"),
        permissions=None,
        user_token="token",
    )

    assert result.columns == build_busca_ativa_header()
    rows = [row async for page in result.pages for row in page]
    assert [(r["id_membro_familia"], r["fonte"]) for r in rows] == [
        ("1", "SMAS"),
        ("1", "SMAS"),
        ("2", "SMS"),
    ]
    assert [r["unidade_smas_nome"] for r in rows] == ["CRAS A", "CRAS B", None]
    assert busca_ativa_repo.received["ids"] == ["1", "2"]
    assert busca_ativa_repo.received["user_token"] == "token"


@pytest.mark.asyncio
async def test_execute_participant_without_events_emits_nothing():
    participant_repo = FakeParticipantRepo([[_page("1"), _page("2")]])
    busca_ativa_repo = FakeBuscaAtivaRepo([("1", _evento())])
    use_case = ExportBuscaAtivaUseCase(participant_repo, busca_ativa_repo)

    result = await use_case.execute(
        filters=FilterCriteria(), sort=SortParams(), permissions=None
    )

    rows = [row async for page in result.pages for row in page]
    assert [r["id_membro_familia"] for r in rows] == ["1"]


@pytest.mark.asyncio
async def test_execute_empty_export_falls_back_to_static_columns():
    use_case = ExportBuscaAtivaUseCase(FakeParticipantRepo([]), FakeBuscaAtivaRepo([]))

    result = await use_case.execute(filters=FilterCriteria(), sort=SortParams())

    assert result.columns == build_busca_ativa_header()
    assert [row async for page in result.pages for row in page] == []


@pytest.mark.asyncio
async def test_execute_raises_repository_errors_eagerly():
    class FailingParticipantRepo:
        async def export_busca_ativa_rows(
            self, filters, sort, permissions=None, user_token=None
        ):
            raise ForbiddenError("Sem acesso")
            yield []  # pragma: no cover

    use_case = ExportBuscaAtivaUseCase(
        FailingParticipantRepo(), FakeBuscaAtivaRepo([])
    )

    with pytest.raises(ForbiddenError):
        await use_case.execute(filters=FilterCriteria(), sort=SortParams())


@pytest.mark.asyncio
async def test_execute_scopes_columns_to_secretaria_access():
    participant_repo = FakeParticipantRepo([[_page("1")]])
    busca_ativa_repo = FakeBuscaAtivaRepo([("1", _evento())])
    use_case = ExportBuscaAtivaUseCase(participant_repo, busca_ativa_repo)

    permissions = UserPermissions(
        cpf="22222222222",
        is_admin=False,
        is_super_admin=False,
        secretarias_acesso=["SMAS"],
    )
    result = await use_case.execute(
        filters=FilterCriteria(),
        sort=SortParams(),
        permissions=permissions,
    )

    assert result.columns == build_busca_ativa_header(permissions)
    assert "sms_tipo_publico" not in result.columns
    assert "unidade_sms_nome" not in result.columns
    assert "smas_tipo" in result.columns


@pytest.mark.asyncio
async def test_execute_passes_filter_fontes_and_scopes_columns():
    participant_repo = FakeParticipantRepo([[_page("1")]])
    busca_ativa_repo = FakeBuscaAtivaRepo([("1", _evento())])
    use_case = ExportBuscaAtivaUseCase(participant_repo, busca_ativa_repo)

    result = await use_case.execute(
        filters=FilterCriteria(busca_ativa="SMAS"),
        sort=SortParams(),
        permissions=None,
    )

    # Filter fontes are forwarded to the repository and prune the columns.
    assert busca_ativa_repo.received["fontes"] == ["SMAS"]
    assert result.columns == build_busca_ativa_header(None, ["SMAS"])
    assert "sms_tipo_publico" not in result.columns
    assert "unidade_sms_nome" not in result.columns
    assert "smas_tipo" in result.columns


@pytest.mark.asyncio
async def test_merge_maps_sms_unidade():
    evento = BuscaAtivaEvento(
        fonte="SMS",
        data=date(2026, 7, 10),
        unidade_referenciada=BuscaAtivaUnidadeReferenciada(
            sms=BuscaAtivaUnidadeSMS(
                nome="CF Felippe", regional="AP 3.3", equipe_nome="Equipe Azul"
            ),
            smas=None,
        ),
    )
    merged = ExportBuscaAtivaUseCase._merge_row(_page("1"), evento)

    assert merged["unidade_sms_nome"] == "CF Felippe"
    assert merged["unidade_sms_equipe"] == "Equipe Azul"
    assert merged["unidade_sms_regional"] == "AP 3.3"
    assert merged["unidade_smas_nome"] is None
