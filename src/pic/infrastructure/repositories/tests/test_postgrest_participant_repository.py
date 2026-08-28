import json
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from src.core.security.permissions_models import UserPermissions
from src.pic.domain.models.filters import FilterCriteria
from src.pic.domain.models.pagination import PaginationParams, SortParams
from src.pic.infrastructure.postgrest_client.client import PostgrestClient
from src.pic.infrastructure.postgrest_client.config import PostgrestClientConfig
from src.pic.infrastructure.postgrest_client.errors import PostgrestError
from src.pic.infrastructure.repositories.postgrest_participant_repository import (
    PostgrestParticipantRepository,
)

CONFIG = PostgrestClientConfig(
    base_url="https://data-proxy.example/",
    schema="app_pequenos_cariocas",
    token_url="https://keycloak.example/token",
    client_id="pic-client",
    client_secret="pic-secret",
)

USER_TOKEN = "user-jwt-token"

SUPER_ADMIN = UserPermissions(
    cpf="11111111111", is_admin=True, is_super_admin=True, secretarias_acesso=[]
)

PARTIAL_SMS = UserPermissions(
    cpf="22222222222",
    is_admin=False,
    is_super_admin=False,
    secretarias_acesso=["SMS"],
)

NO_ACCESS = UserPermissions(
    cpf="33333333333",
    is_admin=False,
    is_super_admin=False,
    secretarias_acesso=[],
)


def resumo_row(membro_id: str, bairro: str = "Centro", situacao: str = "Atenção", **overrides):
    """One `endpoint_participante_resumo` row (pre-aggregated counters)."""
    row = {
        "id_familia": f"FAM-{membro_id}",
        "id_membro_familia": membro_id,
        "nome": f"NOME {membro_id}",
        "cpf": f"{int(membro_id):011d}",
        "grupo": "Criança",
        "bairro": bairro,
        "idade": 3,
        "status": "Ativo",
        "situacao": situacao,
        "raca": "branca",
        "total_fracao": "7/7",
        "assistencia_fracao": "3/3",
        "educacao_fracao": "0/0",
        "saude_fracao": "4/4",
        "total_protocolos_irregular": 0,
        "total_protocolos_regular": 7,
        "assistencia_protocolos_total": 3,
        "assistencia_protocolos_regular": 3,
        "assistencia_protocolos_irregular": 0,
        "educacao_protocolos_total": 0,
        "educacao_protocolos_regular": 0,
        "educacao_protocolos_irregular": 0,
        "saude_protocolos_total": 4,
        "saude_protocolos_regular": 4,
        "saude_protocolos_irregular": 0,
    }
    row.update(overrides)
    return row


def protocolo_row(
    membro_id: str,
    *,
    protocolo_id: str = "sms_x",
    secretaria: str = "SMS",
    status_label: str = "Regular",
):
    return {
        "id_membro_familia": membro_id,
        "protocolo_id": protocolo_id,
        "protocolo_secretaria": secretaria,
        "protocolo_descricao": "descricao",
        "protocolo_status": "regular",
        "protocolo_irregular_indicador": False,
        "protocolo_status_label": status_label,
        "cpf_particao": 1,
    }


class FakeDataProxy:
    """Fakes the data-proxy PostgREST behind one MockTransport.

    Honors limit/offset and simple column filters (`eq.`, `ilike.`, `in.`,
    `is.`) over the canned rows per table, and returns a Content-Range header
    when the request carries `Prefer: count=exact`.
    """

    def __init__(self, rows_by_table: dict[str, list[dict]]):
        self.rows_by_table = rows_by_table
        self.requests: list[httpx.Request] = []
        self.error_status: int | None = None
        self.error_body: dict | None = None
        self.error_text: str | None = None
        self.transport_error: Exception | None = None

    @staticmethod
    def _matches(row: dict, params: httpx.QueryParams) -> bool:
        for key, value in params.items():
            if key in {"select", "order", "limit", "offset"}:
                continue
            if not isinstance(value, str) or "." not in value:
                continue
            op, _, operand = value.partition(".")
            if op not in {"eq", "ilike", "in", "is"}:
                continue
            row_value = row.get(key)
            if op == "eq":
                if str(row_value) != operand:
                    return False
            elif op == "ilike":
                pattern = (
                    operand.replace("\\_", "_")
                    .replace("\\%", "%")
                    .replace("\\\\", "\\")
                )
                if str(row_value or "").lower() != pattern.lower():
                    return False
            elif op == "in":
                allowed = [v.strip() for v in operand.strip("()").split(",")]
                if str(row_value) not in allowed:
                    return False
            elif op == "is":
                if bool(row_value) != (operand == "true"):
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
            if self.error_text is not None:
                return httpx.Response(
                    self.error_status, text=self.error_text, request=request
                )
            return httpx.Response(
                self.error_status,
                json=self.error_body
                or {"message": "boom", "code": "500", "hint": None, "details": None},
                request=request,
            )

        table = request.url.path.lstrip("/")
        rows = [
            row
            for row in self.rows_by_table.get(table, [])
            if self._matches(row, request.url.params)
        ]
        params = request.url.params
        limit = int(params["limit"]) if "limit" in params else None
        offset = int(params["offset"]) if "offset" in params else 0
        page = rows[offset : offset + limit] if limit is not None else rows[offset:]

        headers = {}
        if "count=exact" in request.headers.get("prefer", ""):
            headers["Content-Range"] = f"{offset}-{len(rows)}/{len(rows)}"
        return httpx.Response(200, json=page, headers=headers, request=request)


@pytest.fixture
def make_repo():
    def _make(
        rows_by_table: dict[str, list[dict]],
        redis_client=None,
    ) -> tuple[PostgrestParticipantRepository, FakeDataProxy]:
        fake = FakeDataProxy(rows_by_table)
        client = PostgrestClient(CONFIG, transport=httpx.MockTransport(fake))
        return (
            PostgrestParticipantRepository(client, redis_client=redis_client),
            fake,
        )

    return _make


# ---------------------------------------------------------------------------
# List — super admin (full access, pushdown)
# ---------------------------------------------------------------------------


async def test_list_pushes_filters_sort_pagination_and_user_token(make_repo):
    rows = [
        resumo_row("1", bairro="Engenho da Rainha", id_cre="03"),
        resumo_row("2", bairro="Engenho da Rainha", id_cre="03"),
    ]
    repo, fake = make_repo({"endpoint_participante_resumo": rows})

    data, meta = await repo.list_participants(
        filters=FilterCriteria(status="Ativo", bairro="Engenho da Rainha", cre="03"),
        pagination=PaginationParams(page=2, page_size=50),
        sort=SortParams(sort_by="bairro", sort_order="desc"),
        permissions=SUPER_ADMIN,
        user_token=USER_TOKEN,
    )

    sent = fake.requests[0]
    assert sent.headers["authorization"] == f"Bearer {USER_TOKEN}"
    assert sent.headers["accept-profile"] == "app_pequenos_cariocas"
    params = sent.url.params
    select = params["select"]
    assert select.startswith("id_familia,id_membro_familia,nome,cpf,grupo,bairro,idade,status,raca")
    assert "situacao" in select
    assert "total_fracao" in select
    assert "total_protocolos_irregular" in select
    assert params["status"] == "ilike.Ativo"
    assert params["bairro"] == "ilike.Engenho da Rainha"
    assert params["id_cre"] == "eq.03"
    assert params["order"] == ("bairro.desc.nullslast,id_membro_familia.asc.nullslast")
    assert params["limit"] == "50"
    assert params["offset"] == "50"
    assert "count=exact" in sent.headers["prefer"]

    # Page 2 of a 2-row set is empty (server-side offset applies); the count
    # still reflects the full filtered set.
    assert data == []
    assert meta.page == 2
    assert meta.page_size == 50
    assert meta.total_rows == 2
    assert meta.total_pages == 1
    assert meta.cache_hit is False
    assert meta.can_view_dashboard is None
    assert meta.profiling["filters_applied"] == 3


async def test_list_multi_value_filter_uses_in(make_repo):
    repo, fake = make_repo({"endpoint_participante_resumo": []})
    await repo.list_participants(
        filters=FilterCriteria(bairro="A|B"),
        pagination=PaginationParams(page=1, page_size=20),
        sort=SortParams(),
        permissions=SUPER_ADMIN,
    )
    assert fake.requests[0].url.params["bairro"] == "in.(A,B)"


async def test_list_boolean_filter_uses_is(make_repo):
    repo, fake = make_repo({"endpoint_participante_resumo": []})
    await repo.list_participants(
        filters=FilterCriteria(has_bolsa_familia=True),
        pagination=PaginationParams(page=1, page_size=20),
        sort=SortParams(),
        permissions=SUPER_ADMIN,
    )
    assert fake.requests[0].url.params["has_bolsa_familia"] == "is.true"


async def test_list_search_uses_ilike_or_over_four_columns(make_repo):
    repo, fake = make_repo({"endpoint_participante_resumo": []})
    await repo.list_participants(
        filters=FilterCriteria(search="maria"),
        pagination=PaginationParams(page=1, page_size=20),
        sort=SortParams(),
        permissions=SUPER_ADMIN,
    )
    or_param = fake.requests[0].url.params["or"]
    assert or_param == (
        "(nome.ilike.%maria%,cpf.ilike.%maria%,"
        "id_membro_familia.ilike.%maria%,id_familia.ilike.%maria%)"
    )


async def test_list_page_size_minus_one_loops_pages_without_server_pagination(
    make_repo,
):
    rows = [resumo_row(str(i)) for i in range(1500)]
    repo, fake = make_repo({"endpoint_participante_resumo": rows})

    data, meta = await repo.list_participants(
        filters=FilterCriteria(),
        pagination=PaginationParams(page=1, page_size=-1),
        sort=SortParams(),
        permissions=SUPER_ADMIN,
    )

    assert len(data) == 1500
    assert meta.page_size is None
    assert meta.total_pages == 1
    assert meta.total_rows == 1500
    assert len(fake.requests) == 2
    assert fake.requests[0].url.params["limit"] == "1000"
    assert fake.requests[0].url.params["offset"] == "0"
    assert fake.requests[1].url.params["offset"] == "1000"


async def test_list_sorts_by_default_column_when_sort_not_requested(make_repo):
    repo, fake = make_repo({"endpoint_participante_resumo": []})
    await repo.list_participants(
        filters=FilterCriteria(),
        pagination=PaginationParams(page=1, page_size=20),
        sort=SortParams(),
        permissions=SUPER_ADMIN,
    )
    assert fake.requests[0].url.params["order"].startswith("nome.asc")


async def test_list_situacao_filter_is_pushed_for_full_access(make_repo):
    rows = [
        resumo_row("1", situacao="Atenção"),
        resumo_row("2", situacao="Regular"),
    ]
    repo, fake = make_repo({"endpoint_participante_resumo": rows})

    await repo.list_participants(
        filters=FilterCriteria(situacao="ATENÇÃO"),
        pagination=PaginationParams(page=1, page_size=20),
        sort=SortParams(),
        permissions=SUPER_ADMIN,
    )

    assert fake.requests[0].url.params["situacao"] == "ilike.ATENÇÃO"
    assert fake.requests[0].url.params["limit"] == "20"


# ---------------------------------------------------------------------------
# List — partial access (in-app view)
# ---------------------------------------------------------------------------


async def test_list_partial_secretaria_computes_view_and_drops_invisible_rows(
    make_repo,
):
    rows = [
        resumo_row("1", saude_protocolos_total=1, saude_protocolos_regular=1,
                   saude_protocolos_irregular=0, saude_fracao="1/1"),
        resumo_row("2", saude_protocolos_total=0),
    ]
    repo, fake = make_repo({"endpoint_participante_resumo": rows})

    data, meta = await repo.list_participants(
        filters=FilterCriteria(),
        pagination=PaginationParams(page=1, page_size=20),
        sort=SortParams(),
        permissions=PARTIAL_SMS,
        user_token=USER_TOKEN,
    )

    # Fetch-all (in-app pipeline).
    assert fake.requests[0].url.params["limit"] == "1000"
    assert fake.requests[0].headers["authorization"] == f"Bearer {USER_TOKEN}"

    # Only row "1" has SMS protocols; row "2" is dropped.
    assert [item.id_membro_familia for item in data] == ["1"]
    item = data[0]
    assert item.total_protocolos_irregular == 0
    assert item.total_fracao == "1/1"
    assert item.saude_fracao == "1/1"
    assert item.assistencia_fracao is None
    assert item.educacao_fracao is None
    assert item.situacao is None
    assert item.status == "Ativo"
    assert meta.total_rows == 1


async def test_list_partial_select_only_allowed_secretaria_columns(make_repo):
    repo, fake = make_repo({"endpoint_participante_resumo": []})
    await repo.list_participants(
        filters=FilterCriteria(),
        pagination=PaginationParams(page=1, page_size=20),
        sort=SortParams(),
        permissions=PARTIAL_SMS,
    )
    select = fake.requests[0].url.params["select"]
    assert "saude_fracao" in select
    assert "saude_protocolos_total" in select
    assert "assistencia_fracao" not in select
    assert "educacao_fracao" not in select
    assert "situacao" not in select
    assert "status" in select


async def test_list_partial_ignores_situacao_filter(make_repo):
    repo, fake = make_repo({"endpoint_participante_resumo": [resumo_row("1")]})
    await repo.list_participants(
        filters=FilterCriteria(situacao="ATENÇÃO"),
        pagination=PaginationParams(page=1, page_size=20),
        sort=SortParams(),
        permissions=PARTIAL_SMS,
    )
    assert "situacao" not in fake.requests[0].url.params


async def test_list_partial_sort_by_situacao_falls_back_to_nome(make_repo):
    repo, fake = make_repo({"endpoint_participante_resumo": [resumo_row("1")]})
    await repo.list_participants(
        filters=FilterCriteria(),
        pagination=PaginationParams(page=1, page_size=20),
        sort=SortParams(sort_by="situacao", sort_order="asc"),
        permissions=PARTIAL_SMS,
    )
    assert fake.requests[0].url.params["order"].startswith("nome.asc")


async def test_list_no_access_keeps_rows_with_null_protocol_fields(make_repo):
    repo, _ = make_repo({"endpoint_participante_resumo": [resumo_row("1")]})
    data, meta = await repo.list_participants(
        filters=FilterCriteria(),
        pagination=PaginationParams(page=1, page_size=20),
        sort=SortParams(),
        permissions=NO_ACCESS,
    )
    assert meta.total_rows == 1
    item = data[0]
    assert item.status == "Ativo"
    assert item.total_fracao is None
    assert item.total_protocolos_irregular is None
    assert item.saude_fracao is None
    assert item.situacao is None


# ---------------------------------------------------------------------------
# Protocolo filters (endpoint_participante_protocolos_detalhe)
# ---------------------------------------------------------------------------


async def test_list_protocolo_filter_resolves_ids_then_ins_on_resumo(make_repo):
    repo, fake = make_repo(
        {
            "endpoint_participante_resumo": [resumo_row("1"), resumo_row("2")],
            "endpoint_participante_protocolos_detalhe": [protocolo_row("1")],
        }
    )

    data, meta = await repo.list_participants(
        filters=FilterCriteria(protocolo_secretaria="SMS"),
        pagination=PaginationParams(page=1, page_size=20),
        sort=SortParams(),
        permissions=SUPER_ADMIN,
    )

    detalhe_req = fake.requests[0]
    assert detalhe_req.url.path == "/endpoint_participante_protocolos_detalhe"
    assert detalhe_req.url.params["protocolo_secretaria"] == "ilike.SMS"
    assert "protocolo_secretaria=in" not in str(detalhe_req.url.params)

    resumo_req = fake.requests[1]
    assert resumo_req.url.path == "/endpoint_participante_resumo"
    assert resumo_req.url.params["id_membro_familia"] == "in.(1)"
    assert [item.id_membro_familia for item in data] == ["1"]
    assert meta.total_rows == 1


async def test_list_protocolo_filter_restricts_to_allowed_secretaria_for_partial(
    make_repo,
):
    repo, fake = make_repo(
        {
            "endpoint_participante_resumo": [resumo_row("1")],
            "endpoint_participante_protocolos_detalhe": [
                protocolo_row("1", secretaria="SMS"),
                protocolo_row("1", protocolo_id="sme_x", secretaria="SME"),
            ],
        }
    )

    await repo.list_participants(
        filters=FilterCriteria(protocolo_descricao="sms_x"),
        pagination=PaginationParams(page=1, page_size=20),
        sort=SortParams(),
        permissions=PARTIAL_SMS,
    )

    detalhe_req = fake.requests[0]
    assert detalhe_req.url.params["protocolo_id"] == "ilike.sms\\_x"
    assert detalhe_req.url.params["protocolo_secretaria"] == "in.(SMS)"


async def test_list_protocolo_multi_value_intersects_id_sets(make_repo):
    repo, fake = make_repo(
        {
            "endpoint_participante_resumo": [resumo_row("1"), resumo_row("2")],
            "endpoint_participante_protocolos_detalhe": [
                protocolo_row("1", protocolo_id="sms_a", status_label="Regular"),
                protocolo_row("1", protocolo_id="sms_b", status_label="Atenção"),
                protocolo_row("2", protocolo_id="sms_a", status_label="Regular"),
            ],
        }
    )

    data, _ = await repo.list_participants(
        filters=FilterCriteria(protocolo_status="Regular|Atenção"),
        pagination=PaginationParams(page=1, page_size=20),
        sort=SortParams(),
        permissions=SUPER_ADMIN,
    )

    # Two detail queries (one per value), then the resumo query.
    assert len(fake.requests) == 3
    assert fake.requests[0].url.params["protocolo_status_label"] == "ilike.Regular"
    assert fake.requests[1].url.params["protocolo_status_label"] == "ilike.Atenção"
    assert fake.requests[2].url.params["id_membro_familia"] == "in.(1)"
    assert [item.id_membro_familia for item in data] == ["1"]


async def test_list_protocolo_filter_with_no_matches_returns_empty_without_resumo(
    make_repo,
):
    repo, fake = make_repo(
        {
            "endpoint_participante_resumo": [resumo_row("1")],
            "endpoint_participante_protocolos_detalhe": [],
        }
    )

    data, meta = await repo.list_participants(
        filters=FilterCriteria(protocolo_secretaria="SMS"),
        pagination=PaginationParams(page=1, page_size=20),
        sort=SortParams(),
        permissions=SUPER_ADMIN,
    )

    assert data == []
    assert meta.total_rows == 0
    assert meta.total_pages == 0
    assert len(fake.requests) == 1  # only the detail query


# ---------------------------------------------------------------------------
# Cache (per-user, TTL 1800, skipped in download mode)
# ---------------------------------------------------------------------------


class TestRepositoryCache:
    def _make_redis(self, cached_payload: dict | None = None):
        redis = MagicMock()
        if cached_payload is None:
            redis.get = AsyncMock(return_value=None)
        else:
            redis.get = AsyncMock(
                return_value=json.dumps(cached_payload).encode()
            )
        redis.set = AsyncMock()
        return redis

    @pytest.mark.asyncio
    async def test_cache_miss_writes_to_redis(self, make_repo):
        redis = self._make_redis(None)
        repo, _ = make_repo({"endpoint_participante_resumo": [resumo_row("1")]}, redis_client=redis)
        await repo.list_participants(
            filters=FilterCriteria(),
            pagination=PaginationParams(page=1, page_size=20),
            sort=SortParams(),
            permissions=SUPER_ADMIN,
        )
        redis.set.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_cache_hit_skips_fetches(self, make_repo):
        payload = {
            "data": [],
            "meta": {
                "page": 1,
                "page_size": 20,
                "total_rows": 0,
                "total_pages": 0,
                "cache_hit": False,
                "profiling": None,
                "can_view_dashboard": None,
            },
        }
        redis = self._make_redis(payload)
        repo, fake = make_repo({"endpoint_participante_resumo": []}, redis_client=redis)
        data, meta = await repo.list_participants(
            filters=FilterCriteria(),
            pagination=PaginationParams(page=1, page_size=20),
            sort=SortParams(),
            permissions=SUPER_ADMIN,
        )
        assert len(fake.requests) == 0
        assert data == []
        assert meta.cache_hit is True

    @pytest.mark.asyncio
    async def test_bypass_cache_still_fetches_and_writes(self, make_repo):
        redis = self._make_redis(None)
        repo, fake = make_repo({"endpoint_participante_resumo": [resumo_row("1")]}, redis_client=redis)
        await repo.list_participants(
            filters=FilterCriteria(),
            pagination=PaginationParams(page=1, page_size=20),
            sort=SortParams(),
            permissions=SUPER_ADMIN,
            bypass_cache=True,
        )
        assert len(fake.requests) == 1
        redis.set.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_download_mode_skips_cache(self, make_repo):
        redis = self._make_redis(None)
        repo, _ = make_repo({"endpoint_participante_resumo": [resumo_row("1")]}, redis_client=redis)
        await repo.list_participants(
            filters=FilterCriteria(),
            pagination=PaginationParams(page=1, page_size=-1),
            sort=SortParams(),
            permissions=SUPER_ADMIN,
        )
        redis.get.assert_not_awaited()
        redis.set.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_cache_key_isolates_users(self, make_repo):
        redis = MagicMock()
        redis.get = AsyncMock(return_value=None)
        redis.set = AsyncMock()
        repo, _ = make_repo({"endpoint_participante_resumo": []}, redis_client=redis)

        await repo.list_participants(
            filters=FilterCriteria(),
            pagination=PaginationParams(page=1, page_size=20),
            sort=SortParams(),
            permissions=SUPER_ADMIN,
        )
        await repo.list_participants(
            filters=FilterCriteria(),
            pagination=PaginationParams(page=1, page_size=20),
            sort=SortParams(),
            permissions=PARTIAL_SMS,
        )

        keys = [call.args[0] for call in redis.set.await_args_list]
        assert len(keys) == 2
        assert keys[0] != keys[1]
        assert keys[0].startswith("participants_v2:")


# ---------------------------------------------------------------------------
# Detail (endpoint_participante_listagem — unchanged)
# ---------------------------------------------------------------------------


async def test_get_participant_by_id_maps_row_and_attaches_motivos(make_repo):
    visao = {
        "id_familia": "02159929700",
        "id_membro_familia": "00325420412",
        "nome": "ANA JULIA DE SOUZA DA SILVA",
        "cpf": "23131727756",
        "grupo": "Criança",
        "idade": 3,
        "raca": "branca",
        "nascimento_data": "2022-09-22",
        "endereco": "RUA  MOREIA 6",
        "complemento": None,
        "bairro": "Engenho da Rainha",
        "endereco_sms": {
            "endereco": "RUA PRACA",
            "complemento": None,
            "bairro": "ENGENHO DA RAINHA",
        },
        "cohort": "2025-09-01",
        "status": "Ativo",
        "situacao": "Atenção",
        "latitude": -22.867801,
        "longitude": -43.2931916,
        "total_protocolos": 7,
        "total_fracao": "7/7",
        "saude_fracao": "4/4",
        "protocolo_listagem": [
            {
                "id": "sms_visitas_domiciliares_infantil",
                "secretaria": "SMS",
                "descricao": "Criança com 2 visitas domiciliares anuais",
                "status": "regular",
                "irregular_indicador": False,
                "protocolo_status_label": "Regular",
            },
            {
                "id": "smas_acesso_alimentacao",
                "secretaria": "SMAS",
                "descricao": "alimentacao",
                "status": "atencao",
                "irregular_indicador": True,
                "protocolo_status_label": "Atenção",
            },
        ],
    }
    motivos = [
        {
            "cpf": "23131727756",
            "protocolo_id": "smas_acesso_alimentacao",
            "protocolo_motivo": '{"motivos": ["falta de dados"], "detalhes": {}}',
        }
    ]
    repo, fake = make_repo(
        {
            "endpoint_participante_listagem": [visao],
            "protocolo_detalhes": motivos,
        }
    )

    participante = await repo.get_participant_by_id(
        "00325420412", permissions=SUPER_ADMIN, user_token=USER_TOKEN
    )

    assert participante is not None
    assert participante.id_membro_familia == "00325420412"
    assert participante.nascimento_data.isoformat() == "2022-09-22"
    assert participante.endereco_sms.bairro == "ENGENHO DA RAINHA"
    assert participante.latitude == -22.867801

    irregular = [p for p in participante.protocolo_listagem if p.irregular_indicador]
    assert len(irregular) == 1
    assert irregular[0].protocolo_motivo.motivos == ["falta de dados"]

    detail_req = fake.requests[0]
    assert detail_req.url.path == "/endpoint_participante_listagem"
    assert detail_req.url.params["id_membro_familia"] == "eq.00325420412"
    assert detail_req.headers["authorization"] == f"Bearer {USER_TOKEN}"
    motivos_req = fake.requests[1]
    assert motivos_req.url.path == "/protocolo_detalhes"
    assert motivos_req.url.params["cpf"] == "eq.23131727756"


async def test_get_participant_by_id_returns_none_when_missing(make_repo):
    repo, _ = make_repo({"endpoint_participante_listagem": []})
    result = await repo.get_participant_by_id("nope", permissions=SUPER_ADMIN)
    assert result is None


async def test_get_participant_by_id_partial_secretaria_drops_invisible_row(make_repo):
    visao = {
        "id_membro_familia": "1",
        "cpf": "11111111111",
        "protocolo_listagem": [
            {
                "id": "sme_x",
                "secretaria": "SME",
                "irregular_indicador": "false",
                "protocolo_status_label": "Regular",
            }
        ],
    }
    repo, _ = make_repo({"endpoint_participante_listagem": [visao]})
    result = await repo.get_participant_by_id("1", permissions=PARTIAL_SMS)
    assert result is None


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


async def test_api_error_is_wrapped_in_postgrest_error(make_repo):
    repo, fake = make_repo({"endpoint_participante_resumo": []})
    fake.error_status = 400
    fake.error_body = {
        "message": 'column "bairro" does not exist',
        "code": "42703",
        "details": None,
        "hint": "Perhaps you meant the column bairro.",
    }

    with pytest.raises(PostgrestError) as exc_info:
        await repo.list_participants(
            filters=FilterCriteria(bairro="x"),
            pagination=PaginationParams(page=1, page_size=20),
            sort=SortParams(),
            permissions=SUPER_ADMIN,
        )
    error = exc_info.value
    assert error.message == 'column "bairro" does not exist'
    assert error.code == "42703"
    assert error.hint == "Perhaps you meant the column bairro."


async def test_transport_error_is_wrapped_in_postgrest_error(make_repo):
    repo, fake = make_repo({"endpoint_participante_resumo": []})
    fake.transport_error = httpx.ConnectError("connection refused", request=None)

    with pytest.raises(PostgrestError) as exc_info:
        await repo.list_participants(
            filters=FilterCriteria(),
            pagination=PaginationParams(page=1, page_size=20),
            sort=SortParams(),
            permissions=SUPER_ADMIN,
        )
    assert "Falha de comunicação com o data-proxy" in str(exc_info.value)


async def test_api_error_with_plain_text_body_promotes_details_to_message(make_repo):
    repo, fake = make_repo({"endpoint_participante_resumo": []})
    fake.error_status = 401
    fake.error_text = (
        "Jwt is not in the form of Header.Payload.Signature with two dots "
        "and 3 sections"
    )

    with pytest.raises(PostgrestError) as exc_info:
        await repo.list_participants(
            filters=FilterCriteria(),
            pagination=PaginationParams(page=1, page_size=20),
            sort=SortParams(),
            permissions=SUPER_ADMIN,
        )
    error = exc_info.value
    assert (
        error.message
        == "Jwt is not in the form of Header.Payload.Signature with two dots and 3 sections"
    )
    assert error.code == 401


def test_postgrest_error_from_api_error_promotes_details_when_message_is_generic():
    from postgrest.exceptions import APIError

    error = PostgrestError.from_api_error(
        APIError(
            {
                "message": "JSON could not be generated",
                "code": "403",
                "hint": None,
                "details": "b'permission denied for table endpoint_participante_resumo'",
            }
        )
    )
    assert error.message == "permission denied for table endpoint_participante_resumo"
    assert error.code == "403"
    assert (
        error.details == "b'permission denied for table endpoint_participante_resumo'"
    )


def test_postgrest_error_from_api_error_keeps_structured_message():
    from postgrest.exceptions import APIError

    error = PostgrestError.from_api_error(
        APIError(
            {
                "message": 'column "bairro" does not exist',
                "code": "42703",
                "hint": "Perhaps you meant the column bairro.",
                "details": None,
            }
        )
    )
    assert error.message == 'column "bairro" does not exist'
    assert error.code == "42703"
