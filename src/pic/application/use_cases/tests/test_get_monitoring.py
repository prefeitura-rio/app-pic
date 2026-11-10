"""Unit tests for the monitoring use cases (Acompanhamento semanal).

Covers:
    - group: agregação total/ativo/inativo por semana + motivos
    - series: regular_total (regular+atenção), percentuais, by_status
    - protocols: descoberta da última semana quando week_start é None
    - meta: semanas disponíveis/faltantes, última parcial
    - permissão: mesma regra do dashboard (can_view_monitoring=False)
    - recorte territorial: resolução do valor RAW via agregados do consolidado
    - região sem dados → resultado vazio sem consultar a tabela semanal
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.pic.application.use_cases.get_monitoring import (
    GetMonitoringGroupUseCase,
    GetMonitoringProtocolSeriesUseCase,
    GetMonitoringProtocolsUseCase,
    _build_meta,
    _pct,
)
from src.pic.domain.models.geospatial import CamadaRegularidadeAggregate
from src.pic.domain.models.monitoring import (
    GroupWeekRow,
    MonitoringFilters,
    MotivoInativoRow,
    ProtocolWeekRow,
    ProtocolWeekSummaryRow,
)


def _permissions(access: str = "TODOS", super_admin: bool = True):
    perms = MagicMock()
    perms.is_super_admin = super_admin
    perms.secretaria_acesso = access
    return perms


def _group_row(week: str, status: str, qtd: int, snapshot: str | None = None):
    return GroupWeekRow(week_start=week, snapshot_date=snapshot, status=status, qtd=qtd)


def _protocol_row(
    week: str,
    status: str,
    qtd: int,
    regular: int,
    atencao: int = 0,
    irregular: int = 0,
    snapshot: str | None = None,
):
    return ProtocolWeekRow(
        week_start=week,
        snapshot_date=snapshot,
        status=status,
        protocolo_descricao="Frequência escolar",
        protocolo_secretaria="SME",
        qtd=qtd,
        regular=regular,
        atencao=atencao,
        irregular=irregular,
    )


def _make_group_uc(rows=None, motivos=None, geo_aggs=None):
    repo = MagicMock()
    repo.fetch_group_series = AsyncMock(return_value=rows or [])
    repo.fetch_motivos = AsyncMock(return_value=motivos or [])
    geo = MagicMock()
    geo.fetch_regularidade_por_camada = AsyncMock(return_value=geo_aggs or [])
    return GetMonitoringGroupUseCase(repository=repo, geo_repository=geo), repo, geo


def _make_series_uc(rows=None, geo_aggs=None):
    repo = MagicMock()
    repo.fetch_protocol_series = AsyncMock(return_value=rows or [])
    geo = MagicMock()
    geo.fetch_regularidade_por_camada = AsyncMock(return_value=geo_aggs or [])
    return (
        GetMonitoringProtocolSeriesUseCase(repository=repo, geo_repository=geo),
        repo,
        geo,
    )


def _make_protocols_uc(rows=None, latest=None, geo_aggs=None):
    repo = MagicMock()
    repo.fetch_protocols_summary = AsyncMock(return_value=rows or [])
    repo.fetch_latest_week = AsyncMock(return_value=latest)
    geo = MagicMock()
    geo.fetch_regularidade_por_camada = AsyncMock(return_value=geo_aggs or [])
    return (
        GetMonitoringProtocolsUseCase(repository=repo, geo_repository=geo),
        repo,
        geo,
    )


# ---------------------------------------------------------------------------
# Helpers puros
# ---------------------------------------------------------------------------


class TestHelpers:
    def test_pct(self):
        assert _pct(50, 200) == 25.0
        assert _pct(1, 3) == 33.33
        assert _pct(0, 0) is None
        assert _pct(10, 0) is None

    def test_build_meta_with_gap_and_partial(self):
        rows = [
            ("2026-10-19", "2026-10-25"),
            ("2026-10-19", "2026-10-25"),
            ("2026-11-02", "2026-11-04"),  # semana parcial (terça)
        ]
        meta = _build_meta(rows)
        assert meta.has_data is True
        assert meta.available_weeks == ["2026-10-19", "2026-11-02"]
        assert meta.missing_weeks == ["2026-10-26"]
        assert meta.weeks_count == 2
        assert meta.latest_week_start == "2026-11-02"
        assert meta.latest_snapshot_date == "2026-11-04"
        assert meta.latest_is_partial is True
        # janela estável começa após a lacuna
        assert meta.window_start == "2026-11-02"

    def test_build_meta_complete_week_is_not_partial(self):
        rows = [("2026-10-26", "2026-11-01"), ("2026-10-26", "2026-11-01")]
        meta = _build_meta(rows)
        assert meta.latest_is_partial is False
        assert meta.missing_weeks == []
        assert meta.window_start == "2026-10-26"

    def test_build_meta_window_start_after_last_gap(self):
        """Janela estável = primeira semana da sequência contínua mais recente."""
        rows = [
            ("2026-06-01", "2026-06-06"),
            ("2026-06-08", "2026-06-13"),  # lacuna em 2026-06-15
            ("2026-06-22", "2026-06-27"),
            ("2026-06-29", "2026-07-04"),
            ("2026-07-06", "2026-07-11"),
        ]
        meta = _build_meta(rows)
        assert meta.window_start == "2026-06-22"

    def test_build_meta_window_start_first_when_no_gaps(self):
        rows = [
            ("2026-07-06", "2026-07-11"),
            ("2026-07-13", "2026-07-18"),
            ("2026-07-20", "2026-07-25"),
        ]
        meta = _build_meta(rows)
        assert meta.missing_weeks == []
        assert meta.window_start == "2026-07-06"

    def test_build_meta_empty(self):
        meta = _build_meta([])
        assert meta.has_data is False
        assert meta.available_weeks == []
        assert meta.window_start is None


# ---------------------------------------------------------------------------
# Group
# ---------------------------------------------------------------------------


class TestGroup:
    @pytest.mark.asyncio
    async def test_aggregates_and_motivos(self):
        uc, repo, _geo = _make_group_uc(
            rows=[
                _group_row("2026-10-19", "Ativo", 10, "2026-10-25"),
                _group_row("2026-10-19", "Inativo", 3, "2026-10-25"),
                _group_row("2026-10-26", "Ativo", 12, "2026-11-01"),
            ],
            motivos=[
                MotivoInativoRow(motivo="motivo a", qtd=2),
                MotivoInativoRow(motivo=None, qtd=1),
            ],
        )
        result = await uc.execute(
            filters=MonitoringFilters(), permissions=_permissions()
        )

        assert result.can_view_monitoring is True
        assert len(result.series) == 2
        assert result.series[0].total == 13
        assert result.series[0].ativo == 10
        assert result.series[0].inativo == 3
        assert result.motivos == [
            type(result.motivos[0])(motivo="motivo a", total=2),
            type(result.motivos[0])(motivo="Não informado", total=1),
        ]
        # motivos consultados com a última semana da série
        repo.fetch_motivos.assert_awaited_once_with(
            "2026-10-26", MonitoringFilters(), None, None, False
        )

    @pytest.mark.asyncio
    async def test_denied_without_dashboard_access(self):
        uc, repo, _geo = _make_group_uc()
        result = await uc.execute(
            filters=MonitoringFilters(),
            permissions=_permissions(access="SMS", super_admin=False),
        )
        assert result.can_view_monitoring is False
        assert result.series == []
        repo.fetch_group_series.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_empty_when_no_rows(self):
        uc, repo, _geo = _make_group_uc(rows=[])
        result = await uc.execute(
            filters=MonitoringFilters(), permissions=_permissions()
        )
        assert result.meta.has_data is False
        assert result.series == []
        assert result.motivos == []
        repo.fetch_motivos.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_series_trimmed_to_stable_window(self):
        """Séries fora da janela estável não vão na resposta (payload menor);
        meta.available_weeks continua completo."""
        uc, _repo, _geo = _make_group_uc(
            rows=[
                _group_row("2026-06-01", "Ativo", 10, "2026-06-06"),
                # lacunas em 06-08 e 06-15
                _group_row("2026-06-22", "Ativo", 12, "2026-06-27"),
                _group_row("2026-06-29", "Ativo", 14, "2026-07-04"),
            ]
        )
        result = await uc.execute(
            filters=MonitoringFilters(), permissions=_permissions()
        )
        assert result.meta.window_start == "2026-06-22"
        assert [p.week_start for p in result.series] == [
            "2026-06-22",
            "2026-06-29",
        ]
        assert "2026-06-01" in result.meta.available_weeks


# ---------------------------------------------------------------------------
# Series
# ---------------------------------------------------------------------------


class TestSeries:
    @pytest.mark.asyncio
    async def test_regular_total_percents_and_by_status(self):
        uc, _repo, _geo = _make_series_uc(
            rows=[
                _protocol_row("2026-10-26", "Ativo", 100, 70, atencao=10, irregular=20),
                _protocol_row("2026-10-26", "Inativo", 10, 9, irregular=1),
            ]
        )
        result = await uc.execute(
            protocolo_id="sme_frequencia_escolar",
            filters=MonitoringFilters(),
            permissions=_permissions(),
        )

        assert result.protocolo is not None
        assert result.protocolo.id == "sme_frequencia_escolar"
        assert result.protocolo.descricao == "Frequência escolar"
        assert result.protocolo.secretaria == "SME"
        point = result.series[0]
        assert point.total == 110
        assert point.regular_total == 89  # 79 regular + 10 atenção
        assert point.regular_pct == 80.91  # 89/110
        assert point.irregular_pct == 19.09  # 21/110
        assert set(point.by_status) == {"Ativo", "Inativo"}
        assert point.by_status["Ativo"].total == 100
        assert point.by_status["Ativo"].regular_total == 80  # 70 + 10
        assert point.by_status["Inativo"].regular_total == 9

    @pytest.mark.asyncio
    async def test_pct_none_when_denominator_zero(self):
        uc, _repo, _geo = _make_series_uc(
            rows=[_protocol_row("2026-10-26", "Ativo", 0, 0)]
        )
        result = await uc.execute(
            protocolo_id="x", filters=MonitoringFilters(), permissions=_permissions()
        )
        assert result.series[0].regular_pct is None
        assert result.series[0].irregular_pct is None

    @pytest.mark.asyncio
    async def test_denied(self):
        uc, repo, _geo = _make_series_uc()
        result = await uc.execute(
            protocolo_id="x",
            filters=MonitoringFilters(),
            permissions=_permissions(access="SMS", super_admin=False),
        )
        assert result.can_view_monitoring is False
        repo.fetch_protocol_series.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_series_trimmed_to_stable_window(self):
        uc, _repo, _geo = _make_series_uc(
            rows=[
                _protocol_row("2026-06-01", "Ativo", 5, 3, snapshot="2026-06-06"),
                # lacuna em 06-08/06-15
                _protocol_row("2026-06-22", "Ativo", 6, 4, snapshot="2026-06-27"),
                _protocol_row("2026-06-29", "Ativo", 7, 5, snapshot="2026-07-04"),
            ]
        )
        result = await uc.execute(
            protocolo_id="sme_frequencia_escolar",
            filters=MonitoringFilters(),
            permissions=_permissions(),
        )
        assert result.meta.window_start == "2026-06-22"
        assert [p.week_start for p in result.series] == [
            "2026-06-22",
            "2026-06-29",
        ]

    @pytest.mark.asyncio
    async def test_geral_returns_regularidade_geral_label(self):
        """O pseudo-protocolo 'geral' devolve o rótulo de produto — as linhas
        da tabela têm descricao/secretaria 'geral'."""
        uc, _repo, _geo = _make_series_uc(
            rows=[
                ProtocolWeekRow(
                    week_start="2026-10-26",
                    snapshot_date="2026-11-01",
                    status="Ativo",
                    protocolo_descricao="geral",
                    protocolo_secretaria="geral",
                    qtd=100,
                    regular=50,
                )
            ]
        )
        result = await uc.execute(
            protocolo_id="geral",
            filters=MonitoringFilters(),
            permissions=_permissions(),
        )
        assert result.protocolo is not None
        assert result.protocolo.id == "geral"
        assert result.protocolo.descricao == "Regularidade geral"
        assert result.protocolo.secretaria is None
        assert result.series[0].regular_total == 50


# ---------------------------------------------------------------------------
# Protocols
# ---------------------------------------------------------------------------


class TestProtocols:
    @pytest.mark.asyncio
    async def test_uses_latest_week_when_week_start_is_none(self):
        uc, repo, _geo = _make_protocols_uc(
            latest="2026-10-26",
            rows=[
                ProtocolWeekSummaryRow(
                    protocolo_id="sme_frequencia_escolar",
                    protocolo_descricao="Frequência escolar",
                    protocolo_secretaria="SME",
                    snapshot_date="2026-11-01",
                    qtd=100,
                    regular=70,
                    atencao=10,
                    irregular=20,
                )
            ],
        )
        result = await uc.execute(
            filters=MonitoringFilters(), permissions=_permissions()
        )
        repo.fetch_latest_week.assert_awaited_once()
        assert result.week_start == "2026-10-26"
        assert result.snapshot_date == "2026-11-01"
        proto = result.protocols[0]
        assert proto.regular_total == 80
        assert proto.regular_pct == 80.0
        assert proto.irregular_pct == 20.0

    @pytest.mark.asyncio
    async def test_explicit_week_skips_discovery(self):
        uc, repo, _geo = _make_protocols_uc(rows=[])
        result = await uc.execute(
            filters=MonitoringFilters(),
            permissions=_permissions(),
            week_start="2026-10-19",
        )
        repo.fetch_latest_week.assert_not_awaited()
        assert result.week_start == "2026-10-19"
        assert result.protocols == []

    @pytest.mark.asyncio
    async def test_empty_when_no_latest_week(self):
        uc, repo, _geo = _make_protocols_uc(latest=None)
        result = await uc.execute(
            filters=MonitoringFilters(), permissions=_permissions()
        )
        assert result.week_start is None
        repo.fetch_protocols_summary.assert_not_awaited()


# ---------------------------------------------------------------------------
# Recorte territorial (seleção do mapa)
# ---------------------------------------------------------------------------


class TestTerritorial:
    @pytest.mark.asyncio
    async def test_resolves_raw_region_and_filters_weekly_table(self):
        uc, repo, _geo = _make_group_uc(
            rows=[_group_row("2026-10-26", "Ativo", 5)],
            geo_aggs=[
                CamadaRegularidadeAggregate(
                    regiao="3ª Rio Comprido", total_participantes=10
                )
            ],
        )
        result = await uc.execute(
            filters=MonitoringFilters(camada="ra", regiao=["Rio Comprido"]),
            permissions=_permissions(),
        )
        # O repositório semanal recebe o valor RAW descoberto no consolidado
        repo.fetch_group_series.assert_awaited_once_with(
            MonitoringFilters(camada="ra", regiao=["3ª Rio Comprido"]),
            None,
            None,
            False,
        )
        assert result.series[0].total == 5

    @pytest.mark.asyncio
    async def test_resolves_multiple_regions_ordered(self):
        """Multiselect: cada nome exibido vira RAW; a lista sai ordenada e
        deduplicada para o ``in`` (OR) da tabela semanal."""
        uc, repo, _geo = _make_group_uc(
            rows=[_group_row("2026-10-26", "Ativo", 5)],
            geo_aggs=[
                CamadaRegularidadeAggregate(
                    regiao="3ª Rio Comprido", total_participantes=10
                ),
                CamadaRegularidadeAggregate(
                    regiao="Santa Teresa", total_participantes=20
                ),
            ],
        )
        result = await uc.execute(
            filters=MonitoringFilters(
                camada="ra", regiao=["Santa Teresa", "Rio Comprido", "Rio Comprido"]
            ),
            permissions=_permissions(),
        )
        repo.fetch_group_series.assert_awaited_once_with(
            MonitoringFilters(camada="ra", regiao=["3ª Rio Comprido", "Santa Teresa"]),
            None,
            None,
            False,
        )
        assert result.series[0].total == 5

    @pytest.mark.asyncio
    async def test_partial_missing_region_keeps_found(self):
        """Uma região sem dados é descartada; a que existe segue para a
        tabela semanal (contribui zero para a união)."""
        uc, repo, _geo = _make_group_uc(
            rows=[_group_row("2026-10-26", "Ativo", 5)],
            geo_aggs=[
                CamadaRegularidadeAggregate(regiao="Centro", total_participantes=10)
            ],
        )
        result = await uc.execute(
            filters=MonitoringFilters(
                camada="bairro", regiao=["Inexistente", "Centro"]
            ),
            permissions=_permissions(),
        )
        repo.fetch_group_series.assert_awaited_once_with(
            MonitoringFilters(camada="bairro", regiao=["Centro"]),
            None,
            None,
            False,
        )
        assert result.series[0].total == 5

    @pytest.mark.asyncio
    async def test_region_without_data_returns_empty_without_weekly_query(self):
        uc, repo, _geo = _make_group_uc(
            geo_aggs=[
                CamadaRegularidadeAggregate(
                    regiao="Outro Bairro", total_participantes=10
                )
            ]
        )
        result = await uc.execute(
            filters=MonitoringFilters(camada="bairro", regiao=["Inexistente"]),
            permissions=_permissions(),
        )
        assert result.meta.has_data is False
        assert result.series == []
        repo.fetch_group_series.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_all_missing_regions_returns_empty(self):
        uc, repo, _geo = _make_group_uc(
            geo_aggs=[
                CamadaRegularidadeAggregate(
                    regiao="Outro Bairro", total_participantes=10
                )
            ]
        )
        result = await uc.execute(
            filters=MonitoringFilters(camada="bairro", regiao=["A", "B"]),
            permissions=_permissions(),
        )
        assert result.meta.has_data is False
        assert result.series == []
        repo.fetch_group_series.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_invalid_camada_raises(self):
        uc, _repo, _geo = _make_group_uc()
        with pytest.raises(ValueError):
            await uc.execute(
                filters=MonitoringFilters(camada="x", regiao=["y"]),
                permissions=_permissions(),
            )

    @pytest.mark.asyncio
    async def test_blank_regions_raise(self):
        uc, _repo, _geo = _make_group_uc()
        with pytest.raises(ValueError):
            await uc.execute(
                filters=MonitoringFilters(camada="bairro", regiao=["", " "]),
                permissions=_permissions(),
            )

    @pytest.mark.asyncio
    async def test_no_territorial_skips_geo_repository(self):
        uc, repo, geo = _make_group_uc(rows=[])
        await uc.execute(filters=MonitoringFilters(), permissions=_permissions())
        geo.fetch_regularidade_por_camada.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_region_resolution_ignores_bypass(self):
        """bypass_cache do usuário vale para a tabela semanal, não para a
        resolução do valor RAW (agregação pesada do mapa permanece
        cacheável)."""
        uc, repo, geo = _make_group_uc(
            rows=[_group_row("2026-10-26", "Ativo", 5)],
            geo_aggs=[
                CamadaRegularidadeAggregate(
                    regiao="3ª Rio Comprido", total_participantes=10
                )
            ],
        )
        await uc.execute(
            filters=MonitoringFilters(camada="ra", regiao=["Rio Comprido"]),
            permissions=_permissions(),
            bypass_cache=True,
        )
        geo.fetch_regularidade_por_camada.assert_awaited_once()
        assert (
            geo.fetch_regularidade_por_camada.call_args.kwargs["bypass_cache"] is False
        )
        repo.fetch_group_series.assert_awaited_once_with(
            MonitoringFilters(camada="ra", regiao=["3ª Rio Comprido"]),
            None,
            None,
            True,
        )
