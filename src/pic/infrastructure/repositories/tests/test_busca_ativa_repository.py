"""Tests for the PostgREST busca ativa repository (`endpoint_busca_ativa`).

Covers the query shape (table, select list, `id_membro_familia=eq`, stable
ordering, offset/limit, user token forwarding), the row -> `BuscaAtivaEvento`
mapping (SMAS vs SMS rows, null arrays, `unidade_referenciada`), the
secretaria governance (full/partial/none), and the graceful degradation
(`None`) on API and transport errors.
"""

import httpx
import pytest

from src.core.security.permissions_models import UserPermissions
from src.pic.domain.models.busca_ativa import (
    BuscaAtivaEvento,
    BuscaAtivaUnidadeReferenciada,
    BuscaAtivaUnidadeSMAS,
    BuscaAtivaUnidadeSMS,
)
from src.pic.infrastructure.postgrest_client.client import PostgrestClient
from src.pic.infrastructure.postgrest_client.config import PostgrestClientConfig
from src.pic.infrastructure.postgrest_client.errors import PostgrestError
from src.pic.infrastructure.repositories.busca_ativa_repository import (
    PostgrestBuscaAtivaRepository,
)

CONFIG = PostgrestClientConfig(
    base_url="https://data-proxy.example/",
    schema="app_pequenos_cariocas",
    token_url="https://keycloak.example/token",
    client_id="pic-client",
    client_secret="pic-secret",
)

USER_TOKEN = "user-jwt-token"

TABLE = "endpoint_busca_ativa"

# Sentinel distinguishing "use the helper's default" from an explicit `None`
# (null in the data-proxy row) for the list-valued SMAS fields.
_USE_DEFAULT = object()


def smas_row(
    *,
    id_membro_familia: str = "00325420412",
    id_busca_ativa: str = "abc123",
    data: str = "2026-07-14",
    smas_tipo: list[str] | None = _USE_DEFAULT,
    localizada: bool | None = True,
    protocolo_violado: list[str] | None = _USE_DEFAULT,
    motivo_nao_localizada: list[str] | None = _USE_DEFAULT,
    unidade_referenciada=None,
    **overrides,
) -> dict:
    row = {
        "id_membro_familia": id_membro_familia,
        "id_busca_ativa": id_busca_ativa,
        "fonte": "SMAS",
        "data": data,
        "sms_tipo_publico": None,
        "smas_tipo": ["Por telefone"] if smas_tipo is _USE_DEFAULT else smas_tipo,
        "smas_familia_localizada_indicador": localizada,
        "smas_protocolo_violado": (
            ["Acesso a CPF ou Certidão de Nascimento"]
            if protocolo_violado is _USE_DEFAULT
            else protocolo_violado
        ),
        "smas_motivo_nao_localizada": (
            [] if motivo_nao_localizada is _USE_DEFAULT else motivo_nao_localizada
        ),
        "processed_at": "2026-09-10T20:05:26.795328",
        "unidade_referenciada": unidade_referenciada,
    }
    row.update(overrides)
    return row


def sms_row(
    *,
    id_membro_familia: str = "00325420412",
    id_busca_ativa: str = "def456",
    data: str = "2024-06-19",
    tipo_publico: str | None = "Infancia",
    unidade_referenciada=None,
    **overrides,
) -> dict:
    row = {
        "id_membro_familia": id_membro_familia,
        "id_busca_ativa": id_busca_ativa,
        "fonte": "SMS",
        "data": data,
        "sms_tipo_publico": tipo_publico,
        "smas_tipo": [],
        "smas_familia_localizada_indicador": None,
        "smas_protocolo_violado": [],
        "smas_motivo_nao_localizada": [],
        "processed_at": "2026-09-10T20:05:26.795328",
        "unidade_referenciada": unidade_referenciada,
    }
    row.update(overrides)
    return row


def smas_unidade() -> dict:
    return {
        "sms": None,
        "sme": {"nome": "ESCOLA X", "regional": "1"},
        "smas": {"nome": "CRAS Madureira", "regional": "AP 3.3"},
    }


def sms_unidade() -> dict:
    return {
        "sms": {
            "nome": "CF Felippe Cardoso",
            "regional": "AP 3.3",
            "equipe_nome": "Equipe Azul",
        },
        "sme": None,
        "smas": None,
    }


class FakeDataProxy:
    """Fakes the data-proxy PostgREST behind one MockTransport.

    Honors `eq.` and `in.(...)` column filters over the canned rows; enough
    for the busca ativa repository (single table, member + fonte filters).
    """

    def __init__(self, rows: list[dict]):
        self.rows = rows
        self.requests: list[httpx.Request] = []
        self.error_status: int | None = None
        self.error_body: dict | None = None
        self.transport_error: Exception | None = None

    @staticmethod
    def _matches(row: dict, params: httpx.QueryParams) -> bool:
        for key, value in params.items():
            if key in {"select", "order", "limit", "offset"}:
                continue
            if not isinstance(value, str) or "." not in value:
                continue
            op, _, operand = value.partition(".")
            if op == "eq":
                if str(row.get(key)) != operand:
                    return False
            elif op == "in":
                allowed = {v.strip() for v in operand.strip("()").split(",")}
                if str(row.get(key)) not in allowed:
                    return False
        return True

    async def __call__(self, request: httpx.Request) -> httpx.Response:
        if request.url.host == "keycloak.example":
            return httpx.Response(
                200,
                json={"access_token": "client-credentials-token", "expires_in": 3600},
            )

        self.requests.append(request)
        if self.transport_error is not None:
            raise self.transport_error
        if self.error_status is not None:
            return httpx.Response(
                self.error_status,
                json=self.error_body or {"message": "boom"},
                request=request,
            )

        rows = [
            row
            for row in self.rows
            if self._matches(row, request.url.params)
        ]
        return httpx.Response(200, json=rows, request=request)


@pytest.fixture
def make_repo():
    def _make(
        rows: list[dict],
    ) -> tuple[PostgrestBuscaAtivaRepository, FakeDataProxy]:
        fake = FakeDataProxy(rows)
        client = PostgrestClient(CONFIG, transport=httpx.MockTransport(fake))
        return PostgrestBuscaAtivaRepository(client), fake

    return _make


@pytest.mark.asyncio
async def test_get_busca_ativa_builds_query_and_maps_smas_row(make_repo):
    repo, fake = make_repo([smas_row(unidade_referenciada=smas_unidade())])

    eventos = await repo.get_busca_ativa("00325420412", user_token=USER_TOKEN)

    assert len(fake.requests) == 1
    request = fake.requests[0]
    assert request.url.path == f"/{TABLE}"
    params = request.url.params
    assert params["id_membro_familia"] == "eq.00325420412"
    assert params["offset"] == "0"
    assert params["limit"] == "20"
    assert params.get_list("order") == [
        "data.desc.nullslast,id_busca_ativa.asc.nullslast"
    ]
    select = params["select"]
    for column in (
        "id_busca_ativa",
        "fonte",
        "data",
        "sms_tipo_publico",
        "smas_tipo",
        "smas_familia_localizada_indicador",
        "smas_protocolo_violado",
        "smas_motivo_nao_localizada",
        "processed_at",
        "unidade_referenciada",
    ):
        assert column in select
    assert "id_membro_familia" not in select
    assert request.headers["authorization"] == f"Bearer {USER_TOKEN}"

    assert len(eventos) == 1
    evento = eventos[0]
    assert isinstance(evento, BuscaAtivaEvento)
    assert evento.id_busca_ativa == "abc123"
    assert evento.fonte == "SMAS"
    assert evento.data.isoformat() == "2026-07-14"
    assert evento.sms_tipo_publico is None
    assert evento.smas_tipo == ["Por telefone"]
    assert evento.smas_familia_localizada_indicador is True
    assert evento.smas_protocolo_violado == [
        "Acesso a CPF ou Certidão de Nascimento"
    ]
    assert evento.smas_motivo_nao_localizada == []
    assert evento.processed_at is not None
    assert evento.unidade_referenciada == BuscaAtivaUnidadeReferenciada(
        sms=None,
        smas=BuscaAtivaUnidadeSMAS(nome="CRAS Madureira", regional="AP 3.3"),
    )


@pytest.mark.asyncio
async def test_get_busca_ativa_maps_sms_row(make_repo):
    repo, _ = make_repo([sms_row(unidade_referenciada=sms_unidade())])

    eventos = await repo.get_busca_ativa("00325420412")

    assert len(eventos) == 1
    evento = eventos[0]
    assert evento.fonte == "SMS"
    assert evento.sms_tipo_publico == "Infancia"
    assert evento.smas_tipo == []
    assert evento.smas_familia_localizada_indicador is None
    assert evento.smas_protocolo_violado == []
    assert evento.smas_motivo_nao_localizada == []
    assert evento.unidade_referenciada == BuscaAtivaUnidadeReferenciada(
        sms=BuscaAtivaUnidadeSMS(
            nome="CF Felippe Cardoso", regional="AP 3.3", equipe_nome="Equipe Azul"
        ),
        smas=None,
    )


@pytest.mark.asyncio
async def test_get_busca_ativa_null_unidade_referenciada_maps_to_none(make_repo):
    repo, _ = make_repo([sms_row(unidade_referenciada=None)])

    eventos = await repo.get_busca_ativa("00325420412")

    assert eventos[0].unidade_referenciada is None


@pytest.mark.asyncio
async def test_get_busca_ativa_null_arrays_map_to_empty_lists(make_repo):
    repo, _ = make_repo(
        [
            smas_row(
                smas_tipo=None,
                protocolo_violado=None,
                motivo_nao_localizada=None,
            )
        ]
    )

    eventos = await repo.get_busca_ativa("00325420412")

    assert eventos[0].smas_tipo == []
    assert eventos[0].smas_protocolo_violado == []
    assert eventos[0].smas_motivo_nao_localizada == []


@pytest.mark.asyncio
async def test_get_busca_ativa_forwards_offset_and_limit(make_repo):
    repo, fake = make_repo([smas_row(), sms_row()])

    await repo.get_busca_ativa(
        "00325420412", user_token=USER_TOKEN, offset=10, limit=5
    )

    request = fake.requests[0]
    assert request.url.params["offset"] == "10"
    assert request.url.params["limit"] == "5"


@pytest.mark.asyncio
async def test_get_busca_ativa_returns_empty_list_when_no_rows(make_repo):
    repo, _ = make_repo([])

    eventos = await repo.get_busca_ativa("00325420412")

    assert eventos == []


@pytest.mark.asyncio
async def test_get_busca_ativa_returns_none_on_api_error(make_repo):
    repo, fake = make_repo([])
    fake.error_status = 500
    fake.error_body = {"message": "boom", "code": "500"}

    eventos = await repo.get_busca_ativa("00325420412")

    assert eventos is None


@pytest.mark.asyncio
async def test_get_busca_ativa_returns_none_on_transport_error(make_repo):
    repo, fake = make_repo([])
    fake.transport_error = httpx.ConnectError("connection refused", request=None)

    eventos = await repo.get_busca_ativa("00325420412")

    assert eventos is None


@pytest.mark.asyncio
async def test_get_busca_ativa_scopes_filter_to_requested_member(make_repo):
    repo, _ = make_repo(
        [
            sms_row(id_membro_familia="111", id_busca_ativa="a"),
            smas_row(id_membro_familia="222", id_busca_ativa="b"),
        ]
    )

    eventos = await repo.get_busca_ativa("222")

    assert len(eventos) == 1
    assert eventos[0].id_busca_ativa == "b"


@pytest.mark.asyncio
async def test_get_busca_ativa_partial_access_filters_fonte(make_repo):
    permissions = UserPermissions(
        cpf="22222222222", is_super_admin=False, secretarias_acesso=["SMS"]
    )
    repo, fake = make_repo(
        [
            sms_row(id_membro_familia="00325420412", id_busca_ativa="a"),
            smas_row(id_membro_familia="00325420412", id_busca_ativa="b"),
        ]
    )

    eventos = await repo.get_busca_ativa(
        "00325420412", user_token=USER_TOKEN, permissions=permissions
    )

    assert fake.requests[0].url.params["fonte"] == "in.(SMS)"
    assert [e.id_busca_ativa for e in eventos] == ["a"]


@pytest.mark.asyncio
async def test_get_busca_ativa_full_access_does_not_filter_fonte(make_repo):
    permissions = UserPermissions(
        cpf="11111111111", is_super_admin=True, secretarias_acesso=[]
    )
    repo, fake = make_repo([sms_row(), smas_row()])

    await repo.get_busca_ativa(
        "00325420412", user_token=USER_TOKEN, permissions=permissions
    )

    assert "fonte" not in fake.requests[0].url.params


@pytest.mark.asyncio
async def test_get_busca_ativa_no_access_returns_empty_without_query(make_repo):
    permissions = UserPermissions(
        cpf="33333333333", is_super_admin=False, secretarias_acesso=[]
    )
    repo, fake = make_repo([sms_row(), smas_row()])

    eventos = await repo.get_busca_ativa(
        "00325420412", user_token=USER_TOKEN, permissions=permissions
    )

    assert eventos == []
    assert fake.requests == []


@pytest.mark.asyncio
async def test_get_busca_ativa_sme_only_access_returns_empty_without_query(make_repo):
    permissions = UserPermissions(
        cpf="44444444444", is_super_admin=False, secretarias_acesso=["SME"]
    )
    repo, fake = make_repo([sms_row(), smas_row()])

    eventos = await repo.get_busca_ativa(
        "00325420412", user_token=USER_TOKEN, permissions=permissions
    )

    assert eventos == []
    assert fake.requests == []


def _member_ids(count: int) -> list[str]:
    return [f"{index:011d}" for index in range(count)]


@pytest.mark.asyncio
async def test_get_busca_ativa_for_members_builds_in_query_and_maps_member_id(
    make_repo,
):
    repo, fake = make_repo(
        [
            sms_row(id_membro_familia="00000000001", id_busca_ativa="a"),
            smas_row(id_membro_familia="00000000002", id_busca_ativa="b"),
        ]
    )

    eventos = await repo.get_busca_ativa_for_members(
        ["00000000001", "00000000002"], user_token=USER_TOKEN
    )

    assert len(fake.requests) == 1
    request = fake.requests[0]
    assert request.url.path == f"/{TABLE}"
    assert request.url.params["id_membro_familia"] == "in.(00000000001,00000000002)"
    assert "id_membro_familia" in request.url.params["select"]
    assert request.url.params.get_list("order") == [
        "data.desc.nullslast,id_busca_ativa.asc.nullslast"
    ]

    assert {member_id for member_id, _ in eventos} == {
        "00000000001",
        "00000000002",
    }
    assert [e.id_busca_ativa for _, e in eventos] == ["a", "b"]


@pytest.mark.asyncio
async def test_get_busca_ativa_for_members_chunks_large_id_lists(make_repo):
    repo, fake = make_repo([])

    ids = _member_ids(600)
    eventos = await repo.get_busca_ativa_for_members(ids, user_token=USER_TOKEN)

    assert eventos == []
    # 600 ids / 250 per chunk = 3 requests.
    assert len(fake.requests) == 3
    for request in fake.requests:
        value = request.url.params["id_membro_familia"]
        assert value.startswith("in.(")
        chunk = value.strip("in.(").strip(")")
        assert len(chunk.split(",")) <= 250


@pytest.mark.asyncio
async def test_get_busca_ativa_for_members_partial_access_filters_fonte(make_repo):
    permissions = UserPermissions(
        cpf="22222222222", is_super_admin=False, secretarias_acesso=["SMS"]
    )
    repo, fake = make_repo(
        [
            sms_row(id_membro_familia="00000000001", id_busca_ativa="a"),
            smas_row(id_membro_familia="00000000001", id_busca_ativa="b"),
        ]
    )

    eventos = await repo.get_busca_ativa_for_members(
        ["00000000001"], user_token=USER_TOKEN, permissions=permissions
    )

    assert fake.requests[0].url.params["fonte"] == "in.(SMS)"
    assert [e.id_busca_ativa for _, e in eventos] == ["a"]


@pytest.mark.asyncio
async def test_get_busca_ativa_for_members_filter_fontes_under_full_access(make_repo):
    repo, fake = make_repo(
        [
            sms_row(id_membro_familia="00000000001", id_busca_ativa="a"),
            smas_row(id_membro_familia="00000000001", id_busca_ativa="b"),
        ]
    )

    eventos = await repo.get_busca_ativa_for_members(
        ["00000000001"], user_token=USER_TOKEN, fontes=["SMAS"]
    )

    assert fake.requests[0].url.params["fonte"] == "in.(SMAS)"
    assert [e.id_busca_ativa for _, e in eventos] == ["b"]


@pytest.mark.asyncio
async def test_get_busca_ativa_for_members_filter_fontes_intersects_access(make_repo):
    permissions = UserPermissions(
        cpf="22222222222", is_super_admin=False, secretarias_acesso=["SMAS"]
    )
    repo, fake = make_repo(
        [
            sms_row(id_membro_familia="00000000001", id_busca_ativa="a"),
            smas_row(id_membro_familia="00000000001", id_busca_ativa="b"),
        ]
    )

    eventos = await repo.get_busca_ativa_for_members(
        ["00000000001"],
        user_token=USER_TOKEN,
        permissions=permissions,
        fontes=["SMAS", "SMS"],
    )

    assert fake.requests[0].url.params["fonte"] == "in.(SMAS)"
    assert [e.id_busca_ativa for _, e in eventos] == ["b"]


@pytest.mark.asyncio
async def test_get_busca_ativa_for_members_filter_fontes_disjoint_returns_empty(
    make_repo,
):
    permissions = UserPermissions(
        cpf="22222222222", is_super_admin=False, secretarias_acesso=["SMAS"]
    )
    repo, fake = make_repo([sms_row(), smas_row()])

    eventos = await repo.get_busca_ativa_for_members(
        ["00000000001"],
        user_token=USER_TOKEN,
        permissions=permissions,
        fontes=["SMS"],
    )

    assert eventos == []
    assert fake.requests == []


@pytest.mark.asyncio
async def test_get_busca_ativa_for_members_no_access_returns_empty_without_query(
    make_repo,
):
    permissions = UserPermissions(
        cpf="33333333333", is_super_admin=False, secretarias_acesso=[]
    )
    repo, fake = make_repo([sms_row(), smas_row()])

    eventos = await repo.get_busca_ativa_for_members(
        ["00000000001"], user_token=USER_TOKEN, permissions=permissions
    )

    assert eventos == []
    assert fake.requests == []


@pytest.mark.asyncio
async def test_get_busca_ativa_for_members_empty_ids_returns_empty_without_query(
    make_repo,
):
    repo, fake = make_repo([sms_row(), smas_row()])

    eventos = await repo.get_busca_ativa_for_members([], user_token=USER_TOKEN)

    assert eventos == []
    assert fake.requests == []


@pytest.mark.asyncio
async def test_get_busca_ativa_for_members_raises_on_api_error(make_repo):
    repo, fake = make_repo([])
    fake.error_status = 500
    fake.error_body = {"message": "boom", "code": "500"}

    with pytest.raises(PostgrestError):
        await repo.get_busca_ativa_for_members(
            ["00000000001"], user_token=USER_TOKEN
        )
