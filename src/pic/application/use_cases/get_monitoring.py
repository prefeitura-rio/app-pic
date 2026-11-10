"""Use case do Acompanhamento semanal (fase temporal do Monitoramento).

Uma operação: ``GetMonitoringProtocolSeriesUseCase`` — série de UM protocolo
com desfechos por status (precedência: regular → atenção → irregular →
nao_priorizado → outros → inativo), ``regular_total = regular + atencao``.
O pseudo-protocolo ``NIVEL_GERAL`` ("geral") seleciona a regularidade geral
(linhas ``nivel='geral'``).

A série é devolvida apenas com a **janela estável** (``meta.window_start``
em diante) — o front descarta o resto; a lista completa de semanas fica em
``meta.available_weeks``/``missing_weeks``.

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
from typing import TypedDict

from src.pic.application.ports.geospatial_repository import IGeospatialRepository
from src.pic.application.ports.monitoring_repository import IMonitoringRepository
from src.pic.domain.models.monitoring import (
    NIVEL_GERAL,
    MonitoringFilters,
    MonitoringMeta,
    MonitoringSeriesOutput,
    ProtocolOption,
    ProtocolPoint,
    StatusSlice,
)
from src.pic.domain.models.territorio import CAMADAS_SUPORTADAS, NORMALIZERS
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


def _iso_day(iso: str) -> date:
    """'2026-07-19' ou '2026-07-19T...' → date (sem repetir split/filter)."""
    return date.fromisoformat(iso.split("T")[0])


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

    start = _iso_day(latest_week)
    missing: list[str] = []
    cursor = _iso_day(available[0])
    while cursor <= start:
        iso = cursor.isoformat()
        if iso not in available:
            missing.append(iso)
        cursor += timedelta(days=7)

    latest_is_partial = latest_snapshot is not None and _iso_day(
        latest_snapshot
    ) < start + timedelta(days=6)

    # Janela estável: sequência contínua mais recente, de trás para frente.
    window_start = available[-1]
    previous = _iso_day(available[-1])
    for week in reversed(available[:-1]):
        current = _iso_day(week)
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


class _StatusBucket(TypedDict):
    qtd: int
    regular: int
    atencao: int
    irregular: int


class _WeekBucket(TypedDict):
    qtd: int
    nao_aplica: int
    regular: int
    atencao: int
    nao_priorizado: int
    irregular: int
    outros: int
    by_status: dict[str, _StatusBucket]


def _nova_semana() -> _WeekBucket:
    return {
        "qtd": 0,
        "nao_aplica": 0,
        "regular": 0,
        "atencao": 0,
        "nao_priorizado": 0,
        "irregular": 0,
        "outros": 0,
        "by_status": {},
    }


class GetMonitoringProtocolSeriesUseCase:
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

        if filters.camada not in CAMADAS_SUPORTADAS:
            raise ValueError(
                f"Camada {filters.camada!r} não suportada "
                f"(esperado: {CAMADAS_SUPORTADAS})"
            )
        normalize = NORMALIZERS[filters.camada]
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
            output = MonitoringSeriesOutput(protocolo=ProtocolOption(id=protocolo_id))
            output.can_view_monitoring = False
            return output

        effective, tem_dados = await self._resolve_filters(
            filters, user_token, user_id, bypass_cache
        )
        if not tem_dados:
            return MonitoringSeriesOutput(protocolo=ProtocolOption(id=protocolo_id))

        rows = await self._repository.fetch_protocol_series(
            protocolo_id, effective, user_token, user_id, bypass_cache
        )

        by_week: defaultdict[str, _WeekBucket] = defaultdict(_nova_semana)
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
            status_bucket = bucket["by_status"].setdefault(
                row.status,
                _StatusBucket(qtd=0, regular=0, atencao=0, irregular=0),
            )
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
