"""Unit tests for PostgrestAtualizacoesRepository.

Mesmo padrão do teste do repositório monitoring: httpx.MockTransport + fake
PostgREST que aplica os filtros básicos (eq/neq/in/not.is/order/limit) sobre
linhas em memória — sem rede nem Redis reais.

Coverage:
    - Q1–Q4: parse das linhas e filtros montados (§6 da doc, pós-B1)
    - cache keys: determinísticas e variam por usuário/parâmetros
    - cache hit/miss
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from src.pic.infrastructure.postgrest_client.client import PostgrestClient
from src.pic.infrastructure.postgrest_client.config import PostgrestClientConfig
from src.pic.infrastructure.repositories.postgrest_atualizacoes_repository import (
    PostgrestAtualizacoesRepository,
    _make_cache_key,
)

CONFIG = PostgrestClientConfig(
    base_url="https://data-proxy.example/",
    schema="app_pequenos_cariocas",
    token_url="https://keycloak.example/token",
    client_id="pic-client",
    client_secret="pic-secret",
)

_TABLE = "endpoint_participante_visao_geral_semanal_protocolos"

_REF = "2026-11-01"
_CMP = "2026-10-25"


def _row(**overrides):
    row = {
        "data_referencia_semana_inicio": _REF,
        "data_referencia_semanal": "2026-11-07",
        "protocolo_id": "PR-014",
        "protocolo_descricao": "Busca ativa",
        "protocolo_secretaria": "geral",
        "nivel": "geral",
        "pic_status": "Ativo",
        "pic_cohort": "2026-10-01",
        "id_cas": "01ª CAS",
        "nome_cas": "01ª CAS",
        "regiao_administrativa": "13ª Meier",
        "bairro": "Meier",
        "qtd": 10,
        "regular": 8,
        "atencao": 1,
        "irregular": 1,
    }
    row.update(overrides)
    return row


class FakeAtualizacoesDataProxy:
    """Fake PostgREST que aplica eq/neq/in/not.is/order/limit.

    A query crua é parseada manualmente — ``httpx`` colapsa parâmetros
    repetidos em ``.params`` (ex.: ``pic_cohort=in.(a,b)`` tem vírgulas
    percent-encoded).
    """

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
        rows = [dict(r) for r in self.rows_by_table.get(table, [])]

        for key, value in self._query_items(request):
            if value.startswith("eq."):
                target = value[3:]
                rows = [r for r in rows if str(r.get(key)) == target]
            elif value.startswith("neq."):
                target = value[4:]
                rows = [r for r in rows if str(r.get(key)) != target]
            elif value.startswith("in."):
                targets = value[3:].strip("()").split(",")
                rows = [r for r in rows if str(r.get(key)) in targets]
            elif value.startswith("not.is."):
                rows = [r for r in rows if r.get(key) not in (None, "null")]
            elif key == "order":
                col, direction = value.rsplit(".", 1)
                rows.sort(key=lambda r: r.get(col), reverse=(direction == "desc"))

        limit = self._query_items(request, as_dict=True).get("limit")
        if limit is not None:
            rows = rows[: int(limit)]

        return httpx.Response(200, json=rows, request=request)

    @staticmethod
    def _query_items(request: httpx.Request, as_dict: bool = False):
        from urllib.parse import unquote

        query = request.url.query.decode() if request.url.query else ""
        if as_dict:
            return {
                unquote(key): unquote(value)
                for part in query.split("&")
                if "=" in part
                for key, value in (tuple(part.split("=", 1)),)
            }
        return [
            (unquote(key), unquote(value))
            for key, value in (
                tuple(part.split("=", 1)) for part in query.split("&") if "=" in part
            )
        ]


def _make_repo(
    rows_by_table: dict[str, list[dict]],
    redis_client=None,
) -> tuple[PostgrestAtualizacoesRepository, FakeAtualizacoesDataProxy]:
    fake = FakeAtualizacoesDataProxy(rows_by_table)
    client = PostgrestClient(CONFIG, transport=httpx.MockTransport(fake))
    return (
        PostgrestAtualizacoesRepository(client, redis_client=redis_client),
        fake,
    )


def _make_redis(cached: object | None = None) -> MagicMock:
    redis = MagicMock()
    if cached is None:
        redis.get = AsyncMock(return_value=None)
    else:
        redis.get = AsyncMock(return_value=json.dumps(cached).encode())
    redis.set = AsyncMock()
    return redis


def _data_params(fake: FakeAtualizacoesDataProxy) -> list[tuple[str, str]]:
    data_reqs = [r for r in fake.requests if r.url.host != "keycloak.example"]
    assert len(data_reqs) == 1
    return fake._query_items(data_reqs[0])


def _params_dict(params: list[tuple[str, str]]) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for key, value in params:
        result.setdefault(key, []).append(value)
    return result


# ---------------------------------------------------------------------------
# Tests: Q1–Q4
# ---------------------------------------------------------------------------


class TestConsultas:
    @pytest.mark.asyncio
    async def test_q1_parses_metrics_and_label(self):
        rows = [
            _row(pic_status="Ativo", qtd=100, regular=70, atencao=10, irregular=20),
            _row(pic_status="Inativo", qtd=50, regular=30, irregular=20),
        ]
        repo, _ = _make_repo({_TABLE: rows})
        result = await repo.fetch_semanas_status(
            "cas", "01ª CAS", [_REF], user_token="tok", user_id="cpf"
        )
        assert len(result) == 2
        ativo = next(r for r in result if r.status == "Ativo")
        assert ativo.qtd == 100
        assert ativo.regular == 70
        assert ativo.atencao == 10
        assert ativo.irregular == 20
        # rótulo da região vem da própria tabela (nome_cas)
        assert ativo.regiao_label == "01ª CAS"

    @pytest.mark.asyncio
    async def test_q1_filters(self):
        repo, fake = _make_repo({_TABLE: []})
        await repo.fetch_semanas_status("cas", "01ª CAS", [_CMP, _REF])
        params = _params_dict(_data_params(fake))
        assert params["nivel"] == ["eq.geral"]
        assert params["protocolo_secretaria"] == ["eq.geral"]
        assert params["id_cas"] == ["eq.01ª CAS"]
        assert params["data_referencia_semana_inicio"] == [f"in.({_CMP},{_REF})"]
        # o select inclui o rótulo para camadas-código
        assert "nome_cas" in params["select"][0]

    @pytest.mark.asyncio
    async def test_q1_sem_label_para_ra(self):
        repo, fake = _make_repo({_TABLE: []})
        await repo.fetch_semanas_status("ra", "13ª Meier", [_REF])
        params = _params_dict(_data_params(fake))
        assert "nome_cas" not in params["select"][0]
        assert params["regiao_administrativa"] == ["eq.13ª Meier"]

    @pytest.mark.asyncio
    async def test_q1_sem_regiao_nao_filtra(self):
        """Sem camada/região o escopo vem da RLS — nenhum filtro territorial."""
        repo, fake = _make_repo({_TABLE: []})
        await repo.fetch_semanas_status(None, None, [_REF])
        params = _params_dict(_data_params(fake))
        assert "id_cas" not in params
        assert "regiao_administrativa" not in params
        assert "bairro" not in params

    @pytest.mark.asyncio
    async def test_q2_filters_ativo_e_parse(self):
        rows = [
            _row(
                nivel="sms_vacinacao_pentavalente",
                protocolo_id="sms_vacinacao_pentavalente",
                protocolo_descricao="Vacinação pentavalente",
                qtd=200,
                regular=150,
                atencao=10,
            )
        ]
        repo, fake = _make_repo({_TABLE: rows})
        result = await repo.fetch_protocolos("cas", "01ª CAS", [_CMP, _REF])
        params = _params_dict(_data_params(fake))
        assert params["nivel"] == ["neq.geral"]
        assert params["pic_status"] == ["eq.Ativo"]
        assert params["id_cas"] == ["eq.01ª CAS"]
        assert params["data_referencia_semana_inicio"] == [f"in.({_CMP},{_REF})"]
        assert len(result) == 1
        assert result[0].protocolo_id == "sms_vacinacao_pentavalente"
        assert result[0].protocolo_descricao == "Vacinação pentavalente"
        assert result[0].regular == 150

    @pytest.mark.asyncio
    async def test_q2_filtra_por_secretarias_de_acesso(self):
        rows = [
            _row(
                nivel="sms_vacinacao_pentavalente",
                protocolo_id="sms_vacinacao_pentavalente",
                protocolo_secretaria="SMS",
            ),
            _row(
                nivel="smas_cadunico_atualizado",
                protocolo_id="smas_cadunico_atualizado",
                protocolo_secretaria="SMAS",
            ),
        ]
        repo, fake = _make_repo({_TABLE: rows})
        result = await repo.fetch_protocolos(
            "cas", "01ª CAS", [_CMP, _REF], secretarias=["SMAS"]
        )
        params = _params_dict(_data_params(fake))
        # RLS recorta unidade, não secretaria — o backend filtra explicitamente
        assert params["protocolo_secretaria"] == ["in.(SMAS)"]
        assert [r.protocolo_id for r in result] == ["smas_cadunico_atualizado"]

    @pytest.mark.asyncio
    async def test_q2_sem_filtro_quando_secretarias_none(self):
        repo, fake = _make_repo({_TABLE: []})
        await repo.fetch_protocolos("cas", "01ª CAS", [_CMP, _REF], secretarias=None)
        params = _params_dict(_data_params(fake))
        assert "protocolo_secretaria" not in params

    @pytest.mark.asyncio
    async def test_q2_lista_vazia_nao_consulta(self):
        repo, fake = _make_repo({_TABLE: []})
        result = await repo.fetch_protocolos(
            "cas", "01ª CAS", [_CMP, _REF], secretarias=[]
        )
        assert result == []
        data_reqs = [r for r in fake.requests if r.url.host != "keycloak.example"]
        assert data_reqs == []

    def test_cache_key_q2_inclui_secretarias(self):
        # Acesso revogado não pode reaproveitar resultado antigo no TTL
        assert _make_cache_key(
            "q2", "cpf", "cas", "01ª CAS", {"semanas": [_REF], "secretarias": ["SMAS"]}
        ) != _make_cache_key(
            "q2", "cpf", "cas", "01ª CAS", {"semanas": [_REF], "secretarias": ["SMS"]}
        )
        assert _make_cache_key(
            "q2", "cpf", "cas", "01ª CAS", {"semanas": [_REF], "secretarias": None}
        ) != _make_cache_key(
            "q2", "cpf", "cas", "01ª CAS", {"semanas": [_REF], "secretarias": ["SMAS"]}
        )

    @pytest.mark.asyncio
    async def test_q3_filters_sem_order_e_limit(self):
        rows = [
            _row(regiao_administrativa="13ª Meier", irregular=312),
            _row(regiao_administrativa="Santa Teresa", irregular=200),
        ]
        repo, fake = _make_repo({_TABLE: rows})
        result = await repo.fetch_foco(
            "cas", "01ª CAS", "regiao_administrativa", [_CMP, _REF]
        )
        params = _params_dict(_data_params(fake))
        assert params["nivel"] == ["eq.geral"]
        assert params["protocolo_secretaria"] == ["eq.geral"]
        assert params["pic_status"] == ["eq.Ativo"]
        assert params["id_cas"] == ["eq.01ª CAS"]
        assert params["data_referencia_semana_inicio"] == [f"in.({_CMP},{_REF})"]
        assert params["regiao_administrativa"] == ["not.is.null"]
        # B1: PostgREST não ordena por alias agregado — sem order/limit
        assert "order" not in params
        assert "limit" not in params
        assert [(r.week_start, r.local) for r in result] == [
            (_REF, "13ª Meier"),
            (_REF, "Santa Teresa"),
        ]

    def test_cache_key_q3_inclui_semanas(self):
        # A janela do seletor entra na chave — N=1 não reaproveita N=4
        assert _make_cache_key(
            "q3", "cpf", "cas", "01ª CAS", {"sub_camada": "bairro", "semanas": [_CMP, _REF]}
        ) != _make_cache_key(
            "q3", "cpf", "cas", "01ª CAS", {"sub_camada": "bairro", "semanas": [_REF]}
        )

    @pytest.mark.asyncio
    async def test_camada_invalida_raises(self):
        repo, _ = _make_repo({_TABLE: []})
        with pytest.raises(ValueError):
            await repo.fetch_semanas_status("estado", "x", [_REF])


# ---------------------------------------------------------------------------
# Tests: cache
# ---------------------------------------------------------------------------


class TestCache:
    @pytest.mark.asyncio
    async def test_cache_hit_skips_postgrest(self):
        cached = [
            {
                "week_start": _REF,
                "status": "Ativo",
                "qtd": 7,
                "regular": 5,
                "atencao": 0,
                "irregular": 2,
                "regiao_label": None,
            }
        ]
        repo, fake = _make_repo({_TABLE: []}, redis_client=_make_redis(cached))
        result = await repo.fetch_semanas_status(
            "cas", "01ª CAS", [_REF], user_id="cpf"
        )
        assert len(result) == 1
        assert result[0].qtd == 7
        data_reqs = [r for r in fake.requests if r.url.host != "keycloak.example"]
        assert data_reqs == []

    def test_cache_key_varia_por_usuario_e_parametros(self):
        base = _make_cache_key("q1", "cpf", "cas", "01ª CAS", {"semanas": [_REF]})
        assert base != _make_cache_key(
            "q1", "outro", "cas", "01ª CAS", {"semanas": [_REF]}
        )
        assert base != _make_cache_key(
            "q1", "cpf", "cas", "03ª CAS", {"semanas": [_REF]}
        )
        assert base != _make_cache_key(
            "q1", "cpf", "cas", "01ª CAS", {"semanas": [_CMP]}
        )
        assert base == _make_cache_key(
            "q1", "cpf", "cas", "01ª CAS", {"semanas": [_REF]}
        )
        assert base != _make_cache_key(
            "q2", "cpf", "cas", "01ª CAS", {"semanas": [_REF]}
        )
