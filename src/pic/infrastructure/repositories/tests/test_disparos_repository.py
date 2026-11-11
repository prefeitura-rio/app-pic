"""Tests for the PostgREST disparos repository (`endpoint_whatsapp_disparo`).

Covers the query shape (table, select list, `id_membro_familia=eq`,
`janela_dias=eq.240`, `disparo_na_janela_indicador=is.true`, user token
forwarding), the row -> `Disparo` mapping (nulls, metadados omission), the
discard of rows with every `disparo_*` column null (no disparo happened),
the exclusion of other windows/out-of-window rows, newest-first ordering,
and the graceful degradation (`None`) on API and transport errors.
"""

import httpx
import pytest

from src.pic.domain.models.disparo import Disparo, DisparoMetadados
from src.pic.infrastructure.postgrest_client.client import PostgrestClient
from src.pic.infrastructure.postgrest_client.config import PostgrestClientConfig
from src.pic.infrastructure.repositories.disparos_repository import (
    PostgrestDisparosRepository,
)

CONFIG = PostgrestClientConfig(
    base_url="https://data-proxy.example/",
    schema="app_pequenos_cariocas",
    token_url="https://keycloak.example/token",
    client_id="pic-client",
    client_secret="pic-secret",
)

USER_TOKEN = "user-jwt-token"

TABLE = "endpoint_whatsapp_disparo"


def disparo_row(
    *,
    id_membro_familia: str = "00325420412",
    janela_dias: int = 240,
    indicador_na_janela: bool = True,
    data: str = "2026-07-24",
    datahora: str = "2026-07-25T13:58:52",
    campanha: str = "Mutirão de Vacinação",
    secretaria: str = "SMS",
    status: str = "ENTREGUE",
    indicador_falha: bool = False,
    total_240d: int = 3,
    entregues_240d: int = 3,
    falhas_240d: int = 0,
    **overrides,
) -> dict:
    row = {
        "id_membro_familia": id_membro_familia,
        "janela_dias": janela_dias,
        "disparo_na_janela_indicador": indicador_na_janela,
        "disparo_data": data,
        "disparo_datahora": datahora,
        "disparo_jornada": campanha,
        "disparo_secretaria_sigla": secretaria,
        "disparo_status": status,
        "disparo_falha_indicador": indicador_falha,
        "disparo_total_quantidade": total_240d,
        "disparo_entregues_quantidade": entregues_240d,
        "disparo_falhas_quantidade": falhas_240d,
    }
    row.update(overrides)
    return row


class FakeDataProxy:
    """Fakes the data-proxy PostgREST behind one MockTransport.

    Honors simple `eq.` and `is.` column filters over the canned rows; enough
    for the disparos repository (single table, one table filter plus the
    fixed window/indicator filters).
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
            elif op == "is":
                # PostgREST `is.true`/`is.false`; `is.true` exclui nulos.
                if row.get(key) is not (operand == "true"):
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
    ) -> tuple[PostgrestDisparosRepository, FakeDataProxy]:
        fake = FakeDataProxy(rows)
        client = PostgrestClient(CONFIG, transport=httpx.MockTransport(fake))
        return PostgrestDisparosRepository(client), fake

    return _make


@pytest.mark.asyncio
async def test_get_disparos_builds_query_and_maps_rows_newest_first(make_repo):
    repo, fake = make_repo(
        [
            disparo_row(
                datahora="2026-07-20T10:00:00",
                campanha="Campanha Antiga",
                secretaria="SMAS",
                status="RESPONDIDO",
            ),
            disparo_row(
                datahora="2026-07-25T13:58:52",
                campanha="Mutirão de Vacinação",
                secretaria="SMS",
                status="ENTREGUE",
            ),
        ]
    )

    disparos = await repo.get_disparos("00325420412", user_token=USER_TOKEN)

    assert len(fake.requests) == 1
    request = fake.requests[0]
    assert request.url.path == f"/{TABLE}"
    params = request.url.params
    assert params["id_membro_familia"] == "eq.00325420412"
    assert params["janela_dias"] == "eq.240"
    assert params["disparo_na_janela_indicador"] == "is.true"
    select = params["select"]
    assert "disparo_jornada" in select
    assert "disparo_secretaria_sigla" in select
    assert "disparo_status" in select
    assert "disparo_falha_indicador" in select
    assert "disparo_total_quantidade" in select
    assert "disparo_entregues_quantidade" in select
    assert "disparo_falhas_quantidade" in select
    assert "id_membro_familia" not in select
    assert request.headers["authorization"] == f"Bearer {USER_TOKEN}"

    assert len(disparos) == 2
    # Newest first.
    assert [d.campanha for d in disparos] == [
        "Mutirão de Vacinação",
        "Campanha Antiga",
    ]
    first = disparos[0]
    assert first.data.isoformat() == "2026-07-24"
    assert first.secretaria == "SMS"
    assert first.status == "ENTREGUE"
    assert first.indicador_falha is False
    assert first.metadados == DisparoMetadados(
        total_ultimos_240d=3, entregues_240d=3, falhas_240d=0
    )


@pytest.mark.asyncio
async def test_get_disparos_discards_rows_with_all_disparo_fields_null(make_repo):
    repo, _ = make_repo(
        [
            disparo_row(
                campanha=None,
                data=None,
                datahora=None,
                secretaria=None,
                status=None,
                indicador_falha=None,
                total_240d=None,
                entregues_240d=None,
                falhas_240d=None,
            )
        ]
    )

    disparos = await repo.get_disparos("00325420412")

    assert disparos == []


@pytest.mark.asyncio
async def test_get_disparos_keeps_valid_rows_and_skips_null_rows(make_repo):
    repo, _ = make_repo(
        [
            disparo_row(
                campanha=None,
                data=None,
                datahora=None,
                secretaria=None,
                status=None,
                indicador_falha=None,
                total_240d=None,
                entregues_240d=None,
                falhas_240d=None,
            ),
            disparo_row(campanha="Mutirão de Vacinação"),
        ]
    )

    disparos = await repo.get_disparos("00325420412")

    assert len(disparos) == 1
    assert disparos[0].campanha == "Mutirão de Vacinação"


@pytest.mark.asyncio
async def test_get_disparos_only_reads_the_240_day_window(make_repo):
    repo, _ = make_repo(
        [
            disparo_row(
                janela_dias=30,
                campanha="Janela de 30 dias",
                datahora="2026-09-10T10:16:58",
            ),
            disparo_row(
                janela_dias=240,
                indicador_na_janela=False,
                campanha="Fora da janela de 240",
                datahora="2026-08-20T10:00:00",
            ),
            disparo_row(
                janela_dias=240,
                indicador_na_janela=True,
                campanha="Dentro da janela de 240",
                datahora="2026-09-10T10:16:58",
            ),
        ]
    )

    disparos = await repo.get_disparos("00325420412")

    assert [d.campanha for d in disparos] == ["Dentro da janela de 240"]


@pytest.mark.asyncio
async def test_get_disparos_partial_metadados_are_kept(make_repo):
    repo, _ = make_repo(
        [
            disparo_row(
                total_240d=5,
                entregues_240d=None,
                falhas_240d=1,
            )
        ]
    )

    disparos = await repo.get_disparos("00325420412")

    assert disparos[0].metadados == DisparoMetadados(
        total_ultimos_240d=5, entregues_240d=None, falhas_240d=1
    )


@pytest.mark.asyncio
async def test_get_disparos_returns_empty_list_when_no_rows(make_repo):
    repo, _ = make_repo([])

    disparos = await repo.get_disparos("00325420412")

    assert disparos == []


@pytest.mark.asyncio
async def test_get_disparos_returns_none_on_api_error(make_repo):
    repo, fake = make_repo([])
    fake.error_status = 500
    fake.error_body = {"message": "boom", "code": "500"}

    disparos = await repo.get_disparos("00325420412")

    assert disparos is None


@pytest.mark.asyncio
async def test_get_disparos_returns_none_on_transport_error(make_repo):
    repo, fake = make_repo([])
    fake.transport_error = httpx.ConnectError(
        "connection refused", request=None
    )

    disparos = await repo.get_disparos("00325420412")

    assert disparos is None


@pytest.mark.asyncio
async def test_get_disparos_scopes_filter_to_requested_member(make_repo):
    repo, _ = make_repo(
        [
            disparo_row(id_membro_familia="111"),
            disparo_row(id_membro_familia="222"),
        ]
    )

    disparos = await repo.get_disparos("222")

    assert len(disparos) == 1
    assert isinstance(disparos[0], Disparo)
