"""Use cases do Acompanhamento semanal (fase temporal do Monitoramento).

Quatro operações, uma classe cada (mesmo padrão do geospatial):

- ``GetMonitoringFiltersUseCase`` — opções do card de filtros (sem
  permissão especial; valores program-wide indicativos).
- ``GetMonitoringGroupUseCase`` — série do grupo (total/ativos/inativos) +
  motivos de inativação da última semana.
- ``GetMonitoringProtocolSeriesUseCase`` — série de UM protocolo com
  desfechos por status (precedência: regular → atenção → irregular →
  nao_priorizado → outros → inativo), ``regular_total = regular + atencao``.
- ``GetMonitoringProtocolsUseCase`` — tabela "todos os protocolos" da
  semana selecionada (uma linha por protocolo; nunca somar entre eles).

As séries (grupo e protocolo) são devolvidas apenas com a **janela estável**
(``meta.window_start`` em diante) — o front descarta o resto; as listas
completas de semanas continuam em ``meta.available_weeks``/``missing_weeks``.

Permissão: mesma regra do dashboard (``is_super_admin`` ou
``secretaria_acesso == TODOS``) — caso contrário, resposta vazia com
``can_view_monitoring = False``.

Recorte territorial: ``camada`` + ``regiao`` (valores exibidos no mapa —
multiselect aceito; múltiplas regiões viram OR). O valor RAW da coluna é
descoberto nos agregados do consolidado (mesma query/cache do mapa) pelo
join normalizado — padrão do ``GetDetalhesRegiaoUseCase``.
"""

from collections import defaultdict
from datetime import date, timedelta

from src.pic.application.ports.geospatial_repository import IGeospatialRepository
from src.pic.application.ports.monitoring_repository import IMonitoringRepository
from src.pic.application.use_cases.get_regularidade_por_camada import (
    _CAMADAS_SUPORTADAS,
    _NORMALIZERS,
)
from src.pic.domain.models.monitoring import (
    NIVEL_GERAL,
    GroupPoint,
    MonitoringFilterOptions,
    MonitoringFilters,
    MonitoringGroupOutput,
    MonitoringMeta,
    MonitoringProtocolsOutput,
    MonitoringSeriesOutput,
    MotivoInativo,
    ProtocolOption,
    ProtocolPoint,
    ProtocolSummary,
    StatusSlice,
)
from src.utils.log import logger


def _can_view(permissions) -> bool:
    """Mesma regra do dashboard (None = sem gate, como no dashboard)."""
    if permissions is None:
        return True
    return permissions.is_super_admin or permissions.secretaria_acesso == "TODOS"


def _pct(numerador: int, denominador: int) -> float | None:
    if denominador <= 0:
        return None
    return round(numerador / denominador * 100, 2)


def _build_meta(rows: list[tuple[str, str | None]]) -> MonitoringMeta:
    """Meta da janela: semanas disponíveis/faltantes + parcialidade da última.

    ``window_start`` marca o início da janela estável: percorre as semanas
    disponíveis da mais recente para trás e para na primeira lacuna.
    """
    if not rows:
        return MonitoringMeta(has_data=False)

    available = sorted({week for week, _snap in rows})
    snapshots = [snap for _week, snap in rows if snap]
    latest_week = available[-1]
    latest_snapshot = max(snapshots) if snapshots else None

    start = date.fromisoformat(latest_week.split("T")[0])
    missing: list[str] = []
    cursor = date.fromisoformat(available[0])
    while cursor <= start:
        iso = cursor.isoformat()
        if iso not in available:
            missing.append(iso)
        cursor += timedelta(days=7)

    latest_is_partial = latest_snapshot is not None and date.fromisoformat(
        latest_snapshot.split("T")[0]
    ) < start + timedelta(days=6)

    # Janela estável: sequência contínua mais recente, de trás para frente.
    window_start = available[-1]
    previous = date.fromisoformat(available[-1].split("T")[0])
    for week in reversed(available[:-1]):
        current = date.fromisoformat(week.split("T")[0])
        if (previous - current).days != 7:
            break
        window_start = week
        previous = current

    return MonitoringMeta(
        latest_week_start=latest_week,
        latest_snapshot_date=latest_snapshot,
        latest_is_partial=latest_is_partial,
        available_weeks=available,
        missing_weeks=missing,
        window_start=window_start,
        weeks_count=len(available),
        has_data=True,
    )


def _denied(
    output: MonitoringGroupOutput | MonitoringSeriesOutput | MonitoringProtocolsOutput,
):
    output.can_view_monitoring = False
    return output


class _BaseMonitoringUseCase:
    """Resolução comum do recorte territorial vindo do mapa."""

    def __init__(
        self,
        repository: IMonitoringRepository,
        geo_repository: IGeospatialRepository,
    ):
        self._repository = repository
        self._geo_repository = geo_repository

    async def _resolve_filters(
        self,
        filters: MonitoringFilters,
        user_token: str | None,
        user_id: str | None,
        bypass_cache: bool,
    ) -> tuple[MonitoringFilters, bool]:
        """Retorna (filtros com regiao RAW, tem_dados).

        ``tem_dados=False`` quando regiões foram pedidas mas nenhuma existe
        nos agregados do consolidado com os filtros atuais (regiões sem
        participantes no escopo do usuário) — a série fica vazia sem
        consultar a tabela semanal.

        Com múltiplas regiões (multiselect do mapa), cada valor exibido é
        resolvido para o RAW; regiões sem dados são descartadas (contribuem
        zero para a união). Se sobrar pelo menos uma, a série é consultada
        com ``in`` (OR) na coluna da camada.
        """
        if not filters.camada or not filters.regiao:
            return filters, True

        if filters.camada not in _CAMADAS_SUPORTADAS:
            raise ValueError(
                f"Camada {filters.camada!r} não suportada "
                f"(esperado: {_CAMADAS_SUPORTADAS})"
            )
        normalize = _NORMALIZERS[filters.camada]
        keys = {normalize(r) for r in filters.regiao}
        keys.discard("")
        if not keys:
            raise ValueError(
                f"Regiões inválidas para a camada {filters.camada!r}: "
                f"{filters.regiao!r}"
            )

        aggregates = await self._geo_repository.fetch_regularidade_por_camada(
            camada=filters.camada,
            user_token=user_token,
            user_id=user_id,
            # bypass_cache SEMPRE False: a agregação do mapa é pesada e o
            # valor RAW da região é estável — o bypass do usuário vale para
            # a tabela semanal, não para esta resolução.
            bypass_cache=False,
            status=filters.status,
            cohortes=filters.cohort,
            grupo=filters.grupo,
            has_bolsa_familia=filters.has_bolsa_familia,
        )
        raw_by_key = {normalize(agg.regiao): agg.regiao for agg in aggregates}
        resolved = sorted({raw_by_key[key] for key in keys if key in raw_by_key})
        if not resolved:
            return filters, False
        return filters.model_copy(update={"regiao": resolved}), True


class GetMonitoringFiltersUseCase:
    def __init__(self, repository: IMonitoringRepository):
        self._repository = repository

    async def execute(
        self,
        user_token: str | None = None,
        bypass_cache: bool = False,
    ) -> MonitoringFilterOptions:
        return await self._repository.fetch_filter_options(
            user_token=user_token,
            bypass_cache=bypass_cache,
        )


class GetMonitoringGroupUseCase(_BaseMonitoringUseCase):
    async def execute(
        self,
        filters: MonitoringFilters,
        permissions=None,
        user_token: str | None = None,
        user_id: str | None = None,
        bypass_cache: bool = False,
    ) -> MonitoringGroupOutput:
        if not _can_view(permissions):
            return _denied(MonitoringGroupOutput())

        effective, tem_dados = await self._resolve_filters(
            filters, user_token, user_id, bypass_cache
        )
        if not tem_dados:
            return MonitoringGroupOutput()

        rows = await self._repository.fetch_group_series(
            effective, user_token, user_id, bypass_cache
        )

        motivos: list[MotivoInativo] = []
        if rows:
            latest_week = max(r.week_start for r in rows)
            motivos_rows = await self._repository.fetch_motivos(
                latest_week, effective, user_token, user_id, bypass_cache
            )
            motivos = [
                MotivoInativo(motivo=m.motivo or "Não informado", total=m.qtd)
                for m in motivos_rows
            ]

        by_week: dict[str, dict[str, int]] = defaultdict(
            lambda: {"total": 0, "ativo": 0, "inativo": 0}
        )
        snapshots: dict[str, str | None] = {}
        for row in rows:
            bucket = by_week[row.week_start]
            bucket["total"] += row.qtd
            if row.status == "Ativo":
                bucket["ativo"] += row.qtd
            elif row.status == "Inativo":
                bucket["inativo"] += row.qtd
            snapshots[row.week_start] = row.snapshot_date

        series = [
            GroupPoint(
                week_start=week,
                snapshot_date=snapshots.get(week),
                **by_week[week],
            )
            for week in sorted(by_week)
        ]

        meta = _build_meta([(r.week_start, r.snapshot_date) for r in rows])
        # Série devolvida apenas com a janela estável (o front descarta o
        # resto de qualquer forma); meta.available_weeks continua completo.
        if meta.window_start:
            series = [p for p in series if p.week_start >= meta.window_start]
        logger.info(
            f"[monitoring] group: {len(series)} semanas, "
            f"{len(motivos)} motivos user_id={user_id!r}"
        )
        return MonitoringGroupOutput(meta=meta, series=series, motivos=motivos)


class GetMonitoringProtocolSeriesUseCase(_BaseMonitoringUseCase):
    async def execute(
        self,
        protocolo_id: str,
        filters: MonitoringFilters,
        permissions=None,
        user_token: str | None = None,
        user_id: str | None = None,
        bypass_cache: bool = False,
    ) -> MonitoringSeriesOutput:
        if not _can_view(permissions):
            return _denied(
                MonitoringSeriesOutput(protocolo=ProtocolOption(id=protocolo_id))
            )

        effective, tem_dados = await self._resolve_filters(
            filters, user_token, user_id, bypass_cache
        )
        if not tem_dados:
            return MonitoringSeriesOutput(protocolo=ProtocolOption(id=protocolo_id))

        rows = await self._repository.fetch_protocol_series(
            protocolo_id, effective, user_token, user_id, bypass_cache
        )

        by_week: dict[str, dict] = defaultdict(
            lambda: {
                "qtd": 0,
                "nao_aplica": 0,
                "regular": 0,
                "atencao": 0,
                "nao_priorizado": 0,
                "irregular": 0,
                "outros": 0,
                "by_status": defaultdict(
                    lambda: {
                        "qtd": 0,
                        "regular": 0,
                        "atencao": 0,
                        "irregular": 0,
                    }
                ),
            }
        )
        snapshots: dict[str, str | None] = {}
        for row in rows:
            bucket = by_week[row.week_start]
            bucket["qtd"] += row.qtd
            bucket["nao_aplica"] += row.nao_aplica
            bucket["regular"] += row.regular
            bucket["atencao"] += row.atencao
            bucket["nao_priorizado"] += row.nao_priorizado
            bucket["irregular"] += row.irregular
            bucket["outros"] += row.outros
            status_bucket = bucket["by_status"][row.status]
            status_bucket["qtd"] += row.qtd
            status_bucket["regular"] += row.regular
            status_bucket["atencao"] += row.atencao
            status_bucket["irregular"] += row.irregular
            snapshots[row.week_start] = row.snapshot_date

        series: list[ProtocolPoint] = []
        for week in sorted(by_week):
            bucket = by_week[week]
            regular_total = bucket["regular"] + bucket["atencao"]
            series.append(
                ProtocolPoint(
                    week_start=week,
                    snapshot_date=snapshots.get(week),
                    total=bucket["qtd"],
                    nao_aplica=bucket["nao_aplica"],
                    regular=bucket["regular"],
                    atencao=bucket["atencao"],
                    regular_total=regular_total,
                    nao_priorizado=bucket["nao_priorizado"],
                    irregular=bucket["irregular"],
                    outros=bucket["outros"],
                    regular_pct=_pct(regular_total, bucket["qtd"]),
                    irregular_pct=_pct(bucket["irregular"], bucket["qtd"]),
                    by_status={
                        status: StatusSlice(
                            total=slice_data["qtd"],
                            regular=slice_data["regular"],
                            atencao=slice_data["atencao"],
                            regular_total=(
                                slice_data["regular"] + slice_data["atencao"]
                            ),
                            irregular=slice_data["irregular"],
                        )
                        for status, slice_data in bucket["by_status"].items()
                    },
                )
            )

        meta = _build_meta([(r.week_start, r.snapshot_date) for r in rows])
        # Série devolvida apenas com a janela estável (o front descarta o
        # resto de qualquer forma); meta.available_weeks continua completo.
        if meta.window_start:
            series = [p for p in series if p.week_start >= meta.window_start]
        protocolo = None
        if protocolo_id == NIVEL_GERAL:
            # Pseudo-protocolo: as linhas gerais têm descricao/secretaria
            # "geral" — API/UI recebem o rótulo de produto.
            protocolo = ProtocolOption(id=NIVEL_GERAL, descricao="Regularidade geral")
        elif rows:
            # Descrição/secretaria vêm das próprias linhas (constantes por
            # protocolo — viram chave de GROUP BY sem multiplicar linhas).
            protocolo = ProtocolOption(
                id=protocolo_id,
                descricao=rows[0].protocolo_descricao,
                secretaria=rows[0].protocolo_secretaria,
            )
        logger.info(
            f"[monitoring] protocol series {protocolo_id!r}: "
            f"{len(series)} semanas user_id={user_id!r}"
        )
        return MonitoringSeriesOutput(protocolo=protocolo, meta=meta, series=series)


class GetMonitoringProtocolsUseCase(_BaseMonitoringUseCase):
    async def execute(
        self,
        filters: MonitoringFilters,
        permissions=None,
        user_token: str | None = None,
        user_id: str | None = None,
        bypass_cache: bool = False,
        week_start: str | None = None,
        secretaria: str | None = None,
    ) -> MonitoringProtocolsOutput:
        if not _can_view(permissions):
            return _denied(MonitoringProtocolsOutput())

        effective, tem_dados = await self._resolve_filters(
            filters, user_token, user_id, bypass_cache
        )
        if not tem_dados:
            return MonitoringProtocolsOutput()

        week = week_start or await self._repository.fetch_latest_week(
            effective, user_token, user_id, bypass_cache
        )
        if week is None:
            return MonitoringProtocolsOutput()

        rows = await self._repository.fetch_protocols_summary(
            week, secretaria, effective, user_token, user_id, bypass_cache
        )

        snapshot_date: str | None = None
        protocols: list[ProtocolSummary] = []
        for row in rows:
            if snapshot_date is None:
                snapshot_date = row.snapshot_date
            regular_total = row.regular + row.atencao
            protocols.append(
                ProtocolSummary(
                    protocolo_id=row.protocolo_id,
                    protocolo_descricao=row.protocolo_descricao,
                    protocolo_secretaria=row.protocolo_secretaria,
                    total=row.qtd,
                    nao_aplica=row.nao_aplica,
                    regular=row.regular,
                    atencao=row.atencao,
                    regular_total=regular_total,
                    regular_pct=_pct(regular_total, row.qtd),
                    irregular=row.irregular,
                    irregular_pct=_pct(row.irregular, row.qtd),
                )
            )
        # data_referencia_semanal é uniforme na semana (mesmo snapshot para
        # todas as linhas); pega do primeiro protocolo.
        logger.info(
            f"[monitoring] protocols semana {week}: {len(protocols)} "
            f"user_id={user_id!r}"
        )
        return MonitoringProtocolsOutput(
            week_start=week,
            snapshot_date=snapshot_date,
            protocols=protocols,
        )
