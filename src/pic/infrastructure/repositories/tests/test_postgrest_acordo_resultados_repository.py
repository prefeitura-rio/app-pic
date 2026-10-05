"""Unit tests for PostgrestAcordoResultadosRepository.

Uses the same FakeDataProxy pattern from test_postgrest_dashboard_repository
to mock the data-proxy without any real network or Redis.

Coverage:
    - _calculate_acordo_resultados (todas as seções)
    - filtro de corte pic_cohort.lte.2026-03-01 em todas as queries
      (cohort.lte na wide table)
    - cache hit / miss / bypass_cache
    - resultado vazio → modelo zerado
"""

from __future__ import annotations

import json

import httpx
import pytest

from src.pic.domain.models.acordo_resultados import AcordoResultados
from src.pic.infrastructure.postgrest_client.client import PostgrestClient
from src.pic.infrastructure.postgrest_client.config import PostgrestClientConfig
from src.pic.infrastructure.repositories.postgrest_acordo_resultados_repository import (
    PostgrestAcordoResultadosRepository,
    _calculate_acordo_resultados,
    _make_cache_key,
)

# ---------------------------------------------------------------------------
# Shared test config & helpers
# ---------------------------------------------------------------------------

CONFIG = PostgrestClientConfig(
    base_url="https://data-proxy.example/",
    schema="app_pequenos_cariocas",
    token_url="https://keycloak.example/token",
    client_id="pic-client",
    client_secret="pic-secret",
)

_TABLE_CONSOLIDADO = "endpoint_participante_visao_geral_consolidado"
_TABLE_PROTOCOLOS = "endpoint_participante_visao_geral_protocolos"
_TABLE_SERIES = "endpoint_participante_visao_geral_series"
_TABLE_WIDE = "endpoint_participante_protocolos_wide"


class FakeDataProxy:
    """Minimal fake of the data-proxy PostgREST for the acordo repository."""

    def __init__(self, rows_by_table: dict[str, list[dict]]) -> None:
        self.rows_by_table = rows_by_table
        self.requests: list[httpx.Request] = []

    async def __call__(self, request: httpx.Request) -> httpx.Response:
        if request.url.host == "keycloak.example":
            return httpx.Response(
                200,
                json={"access_token": "test-token", "expires_in": 3600},
            )
        self.requests.append(request)

        path = request.url.path.lstrip("/")
        table = path.split(".")[-1]

        if table == _TABLE_CONSOLIDADO:
            select_param = request.url.params.get("select", "")
            if "pic_status_inativo_motivo" in select_param:
                rows = self.rows_by_table.get("motivos", [])
            elif "pic_grupo" in select_param:
                rows = self.rows_by_table.get("grupos", [])
            elif "has_bolsa_familia" in select_param:
                rows = self.rows_by_table.get("bolsa_familia", [])
            else:
                rows = self.rows_by_table.get("totais", [])
        elif table == _TABLE_WIDE:
            select_param = request.url.params.get("select", "")
            if "has_cartao_pic" in select_param:
                rows = self.rows_by_table.get("cartao_pic", [])
            elif "raca" in select_param:
                rows = self.rows_by_table.get("racas", [])
            elif "regiao_administrativa" in select_param:
                rows = self.rows_by_table.get("ras", [])
            else:
                rows = self.rows_by_table.get(table, [])
        else:
            rows = self.rows_by_table.get(table, [])

        return httpx.Response(200, json=rows, request=request)


class FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        return self.store.get(key)

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        self.store[key] = value


def _make_repo(
    rows_by_table: dict[str, list[dict]],
    redis_client: FakeRedis | None = None,
) -> tuple[PostgrestAcordoResultadosRepository, FakeDataProxy]:
    fake = FakeDataProxy(rows_by_table)
    client = PostgrestClient(CONFIG, transport=httpx.MockTransport(fake))
    return (
        PostgrestAcordoResultadosRepository(client, redis_client=redis_client),
        fake,
    )


# ---------------------------------------------------------------------------
# Sample data fixtures (agregados, como viria do PostgREST)
# ---------------------------------------------------------------------------

FIXTURES: dict[str, list[dict]] = {
    "totais": [
        {
            "pic_status": "Ativo",
            "regular_num": 8,
            "irregular_num": 2,
            "den": 10,
        },
        {
            "pic_status": "Inativo",
            "regular_num": 3,
            "irregular_num": 1,
            "den": 4,
        },
    ],
    "motivos": [
        {"pic_status_inativo_motivo": None, "qtd": 2},
        {"pic_status_inativo_motivo": "Mudança de município", "qtd": 1},
    ],
    "grupos": [
        {"pic_grupo": "Criança", "qtd": 5},
        {"pic_grupo": "Gestante", "qtd": 3},
    ],
    "ras": [
        {"categoria": "Madureira", "total": 7},
        {"categoria": "Centro", "total": 3},
    ],
    "cartao_pic": [
        {"has_cartao_pic": True, "count": 5},
        {"has_cartao_pic": False, "count": 4},
        {"has_cartao_pic": None, "count": 3},
    ],
    "bolsa_familia": [
        {"has_bolsa_familia": True, "qtd": 6},
        {"has_bolsa_familia": False, "qtd": 4},
        {"has_bolsa_familia": None, "qtd": 2},
    ],
    _TABLE_PROTOCOLOS: [
        {
            "protocolo_id": "sms_vacinacao",
            "protocolo_descricao": "Vacinação",
            "protocolo_secretaria": "SMS",
            "numerador": 8,
            "denominador": 15,
        },
    ],
    _TABLE_SERIES: [
        {
            "serie_tipo": "geral",
            "data_referencia_mensal": "2025-01-01",
            "numerador": 10,
            "denominador": 14,
        },
        {
            "serie_tipo": "sms",
            "data_referencia_mensal": "2025-01-01",
            "numerador": 5,
            "denominador": 7,
        },
        {
            "serie_tipo": "sme",
            "data_referencia_mensal": "2025-01-01",
            "numerador": 3,
            "denominador": 5,
        },
        {
            "serie_tipo": "smas",
            "data_referencia_mensal": "2025-01-01",
            "numerador": 2,
            "denominador": 2,
        },
    ],
    "racas": [
        {"categoria": "branca", "total": 6},
        {"categoria": "preta", "total": 4},
    ],
}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_acordo_resultados_computes_all_sections():
    repo, _ = _make_repo(FIXTURES)

    acordo = await repo.get_acordo_resultados(user_token="jwt", user_id="123")

    assert isinstance(acordo, AcordoResultados)
    assert acordo.total_participantes == 14

    assert acordo.ativos.total == 10
    assert acordo.ativos.regulares == 8
    assert acordo.ativos.irregulares == 2
    assert acordo.ativos.percentual_regular == 80.0
    assert acordo.ativos.percentual_irregular == 20.0

    assert acordo.inativos.total == 4
    assert acordo.inativos.regulares == 3
    assert acordo.inativos.irregulares == 1
    assert acordo.inativos.percentual_regular == 75.0

    assert len(acordo.protocolos) == 1
    proto = acordo.protocolos[0]
    assert proto.protocolo_id == "sms_vacinacao"
    assert proto.percentual_regular == 53.3
    assert proto.percentual_irregular == 46.7

    assert len(acordo.evolucao_mensal) == 1
    ponto = acordo.evolucao_mensal[0]
    assert ponto.mes == "2025-01"
    assert ponto.todos == 71.4
    assert ponto.saude == 71.4
    assert ponto.educacao == 60.0
    assert ponto.assistencia == 100.0

    assert [m.motivo for m in acordo.motivos_saida] == [
        "Não informado",
        "Mudança de município",
    ]
    assert [m.total for m in acordo.motivos_saida] == [2, 1]

    assert [d.categoria for d in acordo.distribuicao_raca] == ["branca", "preta"]
    assert [d.categoria for d in acordo.distribuicao_grupo] == [
        "Criança",
        "Gestante",
    ]
    assert [d.categoria for d in acordo.distribuicao_ra] == [
        "Madureira",
        "Centro",
    ]
    assert [d.total for d in acordo.distribuicao_ra] == [7, 3]
    assert [d.categoria for d in acordo.distribuicao_cartao_pic] == [
        "Retirado",
        "Não retirado",
        "Sem direito",
    ]
    assert [d.total for d in acordo.distribuicao_cartao_pic] == [5, 4, 3]
    assert [d.categoria for d in acordo.distribuicao_bolsa_familia] == [
        "Sim",
        "Não",
        "Não informado",
    ]
    assert [d.total for d in acordo.distribuicao_bolsa_familia] == [6, 4, 2]

    assert acordo.meta_regularidade == 30.5


@pytest.mark.asyncio
async def test_cohort_cutoff_filter_present_in_all_queries():
    repo, fake = _make_repo(FIXTURES)

    await repo.get_acordo_resultados(user_token="jwt", user_id="123")

    for request in fake.requests:
        path = request.url.path.lstrip("/")
        table = path.split(".")[-1]
        if table == _TABLE_WIDE:
            assert request.url.params.get_list("cohort") == ["lte.2026-03-01"], (
                f"wide table sem cohort.lte: {request.url}"
            )
        elif table in (_TABLE_CONSOLIDADO, _TABLE_PROTOCOLOS, _TABLE_SERIES):
            assert request.url.params.get_list("pic_cohort") == [
                "lte.2026-03-01"
            ], f"{table} sem pic_cohort.lte: {request.url}"


@pytest.mark.asyncio
async def test_protocolos_restritos_a_ativos():
    repo, fake = _make_repo(FIXTURES)

    await repo.get_acordo_resultados(user_token="jwt", user_id="123")

    protocolos_requests = [
        r
        for r in fake.requests
        if r.url.path.lstrip("/").split(".")[-1] == _TABLE_PROTOCOLOS
    ]
    assert protocolos_requests, "nenhuma query de protocolos foi disparada"

    for request in protocolos_requests:
        assert request.url.params.get_list("pic_status") == ["ilike.ativo"], (
            f"protocolos sem pic_status=ilike.ativo: {request.url}"
        )


@pytest.mark.asyncio
async def test_cache_hit_avoids_queries():
    redis = FakeRedis()
    expected = AcordoResultados(total_participantes=99)
    redis.store[_make_cache_key("123")] = expected.model_dump_json()

    repo, fake = _make_repo(FIXTURES, redis_client=redis)

    acordo = await repo.get_acordo_resultados(user_token="jwt", user_id="123")

    assert acordo.total_participantes == 99
    assert fake.requests == []


@pytest.mark.asyncio
async def test_cache_miss_writes_to_redis():
    redis = FakeRedis()
    repo, _ = _make_repo(FIXTURES, redis_client=redis)

    await repo.get_acordo_resultados(user_token="jwt", user_id="123")

    key = _make_cache_key("123")
    assert key in redis.store
    cached = AcordoResultados.model_validate(json.loads(redis.store[key]))
    assert cached.total_participantes == 14


@pytest.mark.asyncio
async def test_bypass_cache_skips_read_but_writes():
    redis = FakeRedis()
    redis.store[_make_cache_key("123")] = (
        AcordoResultados(total_participantes=99).model_dump_json()
    )
    repo, fake = _make_repo(FIXTURES, redis_client=redis)

    acordo = await repo.get_acordo_resultados(
        user_token="jwt", user_id="123", bypass_cache=True
    )

    assert acordo.total_participantes == 14
    assert fake.requests != []


@pytest.mark.asyncio
async def test_empty_result_sets_return_zeroed_model():
    repo, _ = _make_repo({})

    acordo = await repo.get_acordo_resultados(user_token="jwt", user_id="123")

    assert acordo.total_participantes == 0
    assert acordo.ativos.total == 0
    assert acordo.inativos.total == 0
    assert acordo.protocolos == []
    assert acordo.evolucao_mensal == []
    assert acordo.motivos_saida == []
    assert acordo.distribuicao_raca == []
    assert acordo.distribuicao_grupo == []
    assert acordo.distribuicao_ra == []
    assert acordo.distribuicao_cartao_pic == []
    assert acordo.distribuicao_bolsa_familia == []
    assert acordo.meta_regularidade == 30.5


def test_cache_key_isolated_by_user():
    assert _make_cache_key("111") != _make_cache_key("222")
    assert _make_cache_key("111") == _make_cache_key("111")
    assert _make_cache_key(None) == _make_cache_key(None)


def test_calculate_empty_totais_sem_chaves_serie():
    """Evolução mensal tolera meses sem todas as dimensões (defaultdict)."""
    acordo = _calculate_acordo_resultados(
        totais=[],
        motivos=[],
        grupos=[],
        ras=[],
        cartao_pic=[],
        bolsa_familia=[],
        protocolos=[],
        series=[
            {
                "serie_tipo": "geral",
                "mes": "2025-01",
                "numerador": 1,
                "denominador": 2,
            }
        ],
        racas=[],
    )
    assert acordo.evolucao_mensal[0].todos == 50.0
    assert acordo.evolucao_mensal[0].saude == 0.0
    assert acordo.evolucao_mensal[0].educacao == 0.0
    assert acordo.evolucao_mensal[0].assistencia == 0.0
