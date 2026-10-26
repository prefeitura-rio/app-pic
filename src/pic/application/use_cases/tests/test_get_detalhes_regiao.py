"""Unit tests for GetDetalhesRegiaoUseCase (fase 3j).

Covers:
    - geral derivado dos agregados do consolidado (join normalizado) + taxa
    - descoberta do valor RAW da coluna (ex.: "3ª Rio Comprido" para RA) e
      repasse ao fetch_protocolos_por_regiao
    - protocolos ordenados por secretaria/descrição
    - região sem dados → geral None e protocolos vazios (sem chamada extra)
    - camada/região inválidas → ValueError
    - forward de user_token/user_id/bypass_cache/status/cohortes
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.pic.application.use_cases.get_detalhes_regiao import (
    GetDetalhesRegiaoUseCase,
)
from src.pic.domain.models.geospatial import (
    CamadaRegularidadeAggregate,
    RegiaoProtocoloAggregate,
    RegiaoRegularidadeResumo,
)


def _agg(regiao: str, regulares: int, irregulares: int) -> CamadaRegularidadeAggregate:
    return CamadaRegularidadeAggregate(
        regiao=regiao,
        total_participantes=regulares + irregulares,
        total_regulares=regulares,
        total_irregulares=irregulares,
    )


def _proto(
    protocolo_id: str,
    secretaria: str,
    descricao: str,
    regulares: int,
    participantes: int,
) -> RegiaoProtocoloAggregate:
    return RegiaoProtocoloAggregate(
        protocolo_id=protocolo_id,
        protocolo_secretaria=secretaria,
        protocolo_descricao=descricao,
        total_participantes=participantes,
        total_regulares=regulares,
        total_irregulares=participantes - regulares,
        taxa_regularidade=(
            round(regulares / participantes * 100, 1) if participantes else None
        ),
    )


def _make_use_case(
    aggregates: list[CamadaRegularidadeAggregate],
    protocolos: list[RegiaoProtocoloAggregate] | None = None,
    protocolo_geral: RegiaoRegularidadeResumo | None = None,
):
    fake_repo = MagicMock()
    fake_repo.fetch_regularidade_por_camada = AsyncMock(return_value=aggregates)
    fake_repo.fetch_protocolos_por_regiao = AsyncMock(return_value=protocolos or [])
    fake_repo.fetch_protocolo_geral = AsyncMock(return_value=protocolo_geral)
    return GetDetalhesRegiaoUseCase(repository=fake_repo), fake_repo


class TestGetDetalhesRegiao:
    @pytest.mark.asyncio
    async def test_geral_e_protocolos_da_regiao(self):
        uc, repo = _make_use_case(
            aggregates=[_agg("Centro", 60, 40), _agg("Gamboa", 10, 0)],
            protocolos=[
                _proto("sms_vacinacao_pentavalente", "SMS", "Vacinação", 30, 50),
                _proto("sme_frequencia_escolar", "SME", "Frequência", 10, 20),
            ],
        )
        result = await uc.execute(
            camada="bairro",
            regiao="Centro",
            user_token="jwt",
            user_id="cpf",
            status=["Ativo"],
            cohortes=["2025-03-01"],
        )

        assert result.camada == "bairro"
        assert result.regiao == "Centro"
        assert result.geral is not None
        assert result.geral.total_participantes == 100
        assert result.geral.total_regulares == 60
        assert result.geral.total_irregulares == 40
        assert result.geral.taxa_regularidade == 60.0

        # Repassado o valor RAW encontrado nos agregados + filtros
        repo.fetch_protocolos_por_regiao.assert_awaited_once_with(
            camada="bairro",
            regiao="Centro",
            user_token="jwt",
            user_id="cpf",
            bypass_cache=False,
            status=["Ativo"],
            cohortes=["2025-03-01"],
        )
        # Protocolos ordenados por secretaria/descrição
        assert [p.protocolo_id for p in result.protocolos] == [
            "sme_frequencia_escolar",
            "sms_vacinacao_pentavalente",
        ]

    @pytest.mark.asyncio
    async def test_ra_resolve_ordinal_e_repassa_valor_raw(self):
        uc, repo = _make_use_case(aggregates=[_agg("3ª Rio Comprido", 100, 50)])
        result = await uc.execute(camada="ra", regiao="Rio Comprido")
        assert result.geral is not None
        assert result.geral.total_participantes == 150
        repo.fetch_protocolos_por_regiao.assert_awaited_once_with(
            camada="ra",
            regiao="3ª Rio Comprido",  # raw do consolidado (com ordinal)
            user_token=None,
            user_id=None,
            bypass_cache=False,
            status=None,
            cohortes=None,
        )

    @pytest.mark.asyncio
    async def test_regiao_sem_dados_nao_busca_protocolos(self):
        uc, repo = _make_use_case(aggregates=[_agg("Gamboa", 10, 0)])
        result = await uc.execute(camada="bairro", regiao="Centro")
        assert result.geral is None
        assert result.protocolos == []
        repo.fetch_protocolos_por_regiao.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_camada_invalida_raises(self):
        uc, _ = _make_use_case(aggregates=[])
        with pytest.raises(ValueError, match="não suportada"):
            await uc.execute(camada="municipio", regiao="X")

    @pytest.mark.asyncio
    async def test_regiao_vazia_raises(self):
        uc, _ = _make_use_case(aggregates=[])
        with pytest.raises(ValueError, match="Região inválida"):
            await uc.execute(camada="bairro", regiao="")

    @pytest.mark.asyncio
    async def test_bypass_cache_forwarded(self):
        uc, repo = _make_use_case(aggregates=[_agg("Centro", 1, 1)])
        await uc.execute(camada="bairro", regiao="Centro", bypass_cache=True)
        repo.fetch_regularidade_por_camada.assert_awaited_once()
        kwargs = repo.fetch_regularidade_por_camada.await_args.kwargs
        assert kwargs["bypass_cache"] is True
        assert kwargs["protocolo_id"] is None

    @pytest.mark.asyncio
    async def test_sem_protocolo_nao_busca_media_geral(self):
        uc, repo = _make_use_case(aggregates=[_agg("Centro", 1, 1)])
        result = await uc.execute(camada="bairro", regiao="Centro")
        assert result.protocolo_geral is None
        repo.fetch_protocolo_geral.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_com_protocolo_busca_media_geral_em_paralelo(self):
        uc, repo = _make_use_case(
            aggregates=[_agg("Botafogo", 999, 1)],
            protocolo_geral=RegiaoRegularidadeResumo(
                total_participantes=1000,
                total_regulares=996,
                total_irregulares=4,
                taxa_regularidade=99.6,
            ),
        )
        result = await uc.execute(
            camada="bairro",
            regiao="Botafogo",
            user_token="jwt",
            user_id="cpf",
            status=["Ativo"],
            protocolo_id="smas_acesso_alimentacao",
        )
        repo.fetch_protocolo_geral.assert_awaited_once_with(
            protocolo_id="smas_acesso_alimentacao",
            user_token="jwt",
            user_id="cpf",
            bypass_cache=False,
            status=["Ativo"],
            cohortes=None,
        )
        assert result.protocolo_geral is not None
        assert result.protocolo_geral.taxa_regularidade == 99.6
