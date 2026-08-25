import pytest
from httpx import ASGITransport, AsyncClient

from src.core.security.jwt import get_current_user_permissions_v2, verify_jwt
from src.core.security.permissions_models import UserPermissions
from src.main import app
from src.pic.application.use_cases.list_participants import ParticipantListOutput
from src.pic.domain.errors import NotFoundError
from src.pic.domain.models.pagination import PaginationMeta
from src.pic.domain.models.participante import Participante, ParticipanteListItem
from src.pic.infrastructure.postgrest_client.errors import PostgrestError
from src.pic.presentation.di import (
    get_admin_repo,
    get_list_participants_use_case,
    get_participant_detail_use_case,
)

LIST_ITEM_FIELDS = [
    "id_familia",
    "id_membro_familia",
    "nome",
    "cpf",
    "grupo",
    "bairro",
    "idade",
    "status",
    "situacao",
    "total_fracao",
    "assistencia_fracao",
    "educacao_fracao",
    "saude_fracao",
    "total_protocolos_irregular",
    "raca",
]

PROFILING_FIELDS = [
    "get_dataset_s",
    "cache_hit",
    "apply_filters_s",
    "search_s",
    "filter_options_s",
    "paginate_s",
    "clean_s",
    "convert_to_dict_s",
    "total_pipeline_s",
    "filters_applied",
    "rows_before_filter",
    "rows_after_filter",
    "rows_after_search",
]


def sample_list_item() -> ParticipanteListItem:
    return ParticipanteListItem(
        id_familia="02159929700",
        id_membro_familia="00325420412",
        nome="ANA JULIA DE SOUZA DA SILVA",
        cpf="23131727756",
        grupo="Criança",
        bairro="Engenho da Rainha",
        idade=3,
        status="Ativo",
        situacao="Atenção",
        total_fracao="7/7",
        assistencia_fracao="3/3",
        educacao_fracao="0/0",
        saude_fracao="4/4",
        total_protocolos_irregular=0,
        raca="branca",
    )


def sample_detail() -> Participante:
    return Participante(
        id_familia="02159929700",
        id_membro_familia="00325420412",
        nome="ANA JULIA DE SOUZA DA SILVA",
        cpf="23131727756",
        grupo="Criança",
        idade=3,
        raca="branca",
        nascimento_data="2022-09-22",
        endereco="RUA  MOREIA 6",
        complemento=None,
        bairro="Engenho da Rainha",
        endereco_sms={
            "endereco": "RUA PRACA",
            "complemento": None,
            "bairro": "ENGENHO DA RAINHA",
        },
        telefone_1_ddd="21",
        telefone_1_numero="968267587",
        cohort="2025-09-01",
        status="Ativo",
        situacao="Atenção",
        latitude=-22.867801,
        longitude=-43.2931916,
        total_protocolos=7,
        total_protocolos_irregular=0,
        total_protocolos_atencao=1,
        total_protocolos_regular=6,
        total_fracao="7/7",
        assistencia_fracao="3/3",
        educacao_fracao="0/0",
        saude_fracao="4/4",
        protocolo_listagem=[
            {
                "id": "smas_acesso_alimentacao",
                "secretaria": "SMAS",
                "descricao": "Criança com direito à alimentação adequada disponível",
                "status": "atencao",
                "irregular_indicador": False,
                "protocolo_status_label": "Atenção",
            },
            {
                "id": "sms_consultas_minimas_infantil",
                "secretaria": "SMS",
                "descricao": "Criança com no mínimo 7 consultas no primeiro ano de vida",
                "status": "regular",
                "irregular_indicador": False,
                "protocolo_status_label": "Regular",
            },
        ],
    )


class FakeListUseCase:
    """Records inputs, returns a canned list output (page_size honored)."""

    def __init__(self, error: Exception | None = None, events: list[str] | None = None):
        self.error = error
        self.events = events if events is not None else []
        self.received: dict = {}

    async def execute(
        self,
        filters,
        pagination,
        sort,
        permissions=None,
        bypass_cache=False,
        user_token=None,
    ):
        self.received = {
            "filters": filters,
            "pagination": pagination,
            "sort": sort,
            "user_token": user_token,
        }
        self.events.append("list_use_case")
        if self.error:
            raise self.error
        page_size = None if pagination.page_size == -1 else pagination.page_size
        return ParticipantListOutput(
            data=[sample_list_item()],
            meta=PaginationMeta(
                page=pagination.page,
                page_size=page_size,
                total_rows=1,
                total_pages=1,
                cache_hit=True,
                profiling=dict.fromkeys(PROFILING_FIELDS, 0),
                can_view_dashboard=None,
            ),
        )


class FakeDetailUseCase:
    def __init__(self, error: Exception | None = None, events: list[str] | None = None):
        self.error = error
        self.events = events if events is not None else []
        self.received: dict = {}

    async def execute(
        self,
        id_membro_familia,
        permissions=None,
        bypass_cache=False,
        user_token=None,
    ):
        self.received = {
            "id_membro_familia": id_membro_familia,
            "user_token": user_token,
        }
        self.events.append("detail_use_case")
        if self.error:
            raise self.error
        return sample_detail()


class FakeAdminRepo:
    """Records self-heal calls; no-op otherwise."""

    def __init__(self, events: list[str] | None = None):
        self.events = events if events is not None else []
        self.self_heal_cpfs: list[str] = []

    async def self_heal_policy_sync(self, cpf: str) -> None:
        self.self_heal_cpfs.append(cpf)
        self.events.append("self_heal")


@pytest.fixture
def override_auth():
    token_payload = {"preferred_username": "12345678900"}
    app.dependency_overrides[verify_jwt] = lambda: token_payload
    app.dependency_overrides[get_current_user_permissions_v2] = lambda: UserPermissions(
        cpf="12345678900",
        is_admin=True,
        is_super_admin=True,
        secretarias_acesso=["SME", "SMS", "SMAS"],
    )
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def override_use_cases():
    events: list[str] = []
    list_use_case = FakeListUseCase(events=events)
    detail_use_case = FakeDetailUseCase(events=events)
    admin_repo = FakeAdminRepo(events=events)
    app.dependency_overrides[get_list_participants_use_case] = lambda: list_use_case
    app.dependency_overrides[get_participant_detail_use_case] = lambda: detail_use_case
    app.dependency_overrides[get_admin_repo] = lambda: admin_repo
    yield list_use_case, detail_use_case, admin_repo
    app.dependency_overrides.clear()


@pytest.fixture
async def client(override_auth, override_use_cases):
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={
            "Authorization": "Bearer fake-jwt-token",
            "X-Access-Token": "fake-access-token",
        },
    ) as ac:
        yield ac


@pytest.mark.asyncio
async def test_list_participants_returns_exact_envelope(client, override_use_cases):
    response = await client.get(
        "/api/v2/participants",
        params={"status": "Ativo", "page": "1", "page_size": "50"},
    )

    assert response.status_code == 200
    body = response.json()

    assert set(body.keys()) == {"meta", "data"}
    meta = body["meta"]
    assert meta["page"] == 1
    assert meta["page_size"] == 50
    assert meta["total_rows"] == 1
    assert meta["total_pages"] == 1
    assert meta["cache_hit"] is True
    assert meta["can_view_dashboard"] is None
    assert set(meta["profiling"].keys()) == set(PROFILING_FIELDS)

    assert len(body["data"]) == 1
    item = body["data"][0]
    assert set(item.keys()) == set(LIST_ITEM_FIELDS)
    assert item["id_membro_familia"] == "00325420412"
    assert item["total_protocolos_irregular"] == 0

    list_use_case, _, _ = override_use_cases
    # The access token (X-Access-Token) wins over the id token for the
    # data-proxy call.
    assert list_use_case.received["user_token"] == "fake-access-token"
    assert list_use_case.received["filters"].status == "Ativo"


@pytest.mark.asyncio
async def test_list_participants_download_mode_meta(client):
    response = await client.get("/api/v2/participants", params={"page_size": "-1"})

    assert response.status_code == 200
    meta = response.json()["meta"]
    assert meta["page_size"] is None
    assert meta["total_pages"] == 1


@pytest.mark.asyncio
async def test_list_falls_back_to_id_token_without_access_token_header(
    override_auth, override_use_cases
):
    # Sessões antigas sem o header X-Access-Token: o id_token do
    # Authorization é usado como user_token para o data-proxy.
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"Authorization": "Bearer fake-jwt-token"},
    ) as ac:
        response = await ac.get("/api/v2/participants")

    assert response.status_code == 200
    list_use_case, _, _ = override_use_cases
    assert list_use_case.received["user_token"] == "fake-jwt-token"


@pytest.mark.asyncio
async def test_policy_self_heal_runs_before_list_read(client, override_use_cases):
    response = await client.get("/api/v2/participants")

    assert response.status_code == 200
    _, _, admin_repo = override_use_cases
    assert admin_repo.self_heal_cpfs == ["12345678900"]
    assert admin_repo.events == ["self_heal", "list_use_case"]


@pytest.mark.asyncio
async def test_list_participants_maps_postgrest_error_to_502(
    override_auth,
):
    app.dependency_overrides[get_list_participants_use_case] = lambda: FakeListUseCase(
        error=PostgrestError("data-proxy exploded", code="P0001")
    )
    app.dependency_overrides[get_admin_repo] = lambda: FakeAdminRepo()
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"Authorization": "Bearer fake-jwt-token"},
    ) as ac:
        response = await ac.get("/api/v2/participants")

    assert response.status_code == 502
    assert response.json()["detail"] == "data-proxy exploded"


@pytest.mark.asyncio
async def test_detail_returns_full_envelope(client, override_use_cases):
    response = await client.get("/api/v2/participants/00325420412")

    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == {"data"}
    data = body["data"]
    assert data["id_membro_familia"] == "00325420412"
    assert data["nascimento_data"] == "2022-09-22"
    assert data["complemento"] is None
    assert data["endereco_sms"]["bairro"] == "ENGENHO DA RAINHA"
    protocolos = data["protocolo_listagem"]
    assert len(protocolos) == 2
    assert set(protocolos[0].keys()) == {
        "id",
        "secretaria",
        "descricao",
        "status",
        "irregular_indicador",
        "protocolo_status_label",
    }

    _, detail_use_case, _ = override_use_cases
    assert detail_use_case.received["user_token"] == "fake-access-token"
    assert detail_use_case.received["id_membro_familia"] == "00325420412"


@pytest.mark.asyncio
async def test_detail_maps_not_found_to_404(override_auth):
    app.dependency_overrides[get_participant_detail_use_case] = (
        lambda: FakeDetailUseCase(error=NotFoundError("nao encontrado"))
    )
    app.dependency_overrides[get_admin_repo] = lambda: FakeAdminRepo()
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"Authorization": "Bearer fake-jwt-token"},
    ) as ac:
        response = await ac.get("/api/v2/participants/missing-id")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_detail_maps_postgrest_error_to_502(override_auth):
    app.dependency_overrides[get_participant_detail_use_case] = (
        lambda: FakeDetailUseCase(error=PostgrestError("data-proxy down"))
    )
    app.dependency_overrides[get_admin_repo] = lambda: FakeAdminRepo()
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"Authorization": "Bearer fake-jwt-token"},
    ) as ac:
        response = await ac.get("/api/v2/participants/00325420412")

    assert response.status_code == 502
    assert response.json()["detail"] == "data-proxy down"


@pytest.mark.asyncio
async def test_participants_require_authentication(override_use_cases):
    app.dependency_overrides[verify_jwt] = lambda: {"preferred_username": "x"}
    app.dependency_overrides[get_current_user_permissions_v2] = lambda: UserPermissions(
        cpf="x"
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/api/v2/participants")

    assert response.status_code == 401
