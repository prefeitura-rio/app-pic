"""PostgREST implementation of IMonitoringRepository.

Fonte: ``endpoint_participante_visao_geral_semanal_protocolos`` (agregada por
protocolo/semana, particionada por ``data_referencia_semana_inicio``, janela
móvel de 35 partições).

Design notes:

- Todas as consultas rodam dentro de ``with_user_token`` — a RLS das colunas
  de unidade é aplicada ANTES das agregações, então séries e tabelas respeitam
  o escopo de permissões do usuário.
- Cache Redis: TTL 3600 s; as séries/grupo/protocolos são cacheadas por
  ``user_id`` + filtros (a resposta varia por RLS); as opções de filtro têm
  cache GLOBAL (valores program-wide indicativos — decisão da seção 5.5 do
  documento técnico).
- Agregações do PostgREST: colunas não agregadas no ``select`` viram chaves
  do GROUP BY implícito — ex.: ``select=week,snapshot,pic_status,
  qtd:participante_quantidade.sum()`` agrega por (week, snapshot, status).
- Todas as respostas ficam muito abaixo do limite de 1000 linhas (≤ ~70
  linhas por consulta), mas há guarda defensiva com log.
"""

import asyncio
import hashlib
import json
from typing import Any

from src.pic.application.ports.monitoring_repository import IMonitoringRepository
from src.pic.domain.models.monitoring import (
    CAMADA_COLUMN,
    NIVEL_GERAL,
    PROTOCOLO_TOTAL,
    GroupWeekRow,
    MonitoringFilterOptions,
    MonitoringFilters,
    MonitoringOption,
    MotivoInativoRow,
    ProtocolOption,
    ProtocolWeekRow,
    ProtocolWeekSummaryRow,
)
from src.utils.log import logger

_TABLE = "endpoint_participante_visao_geral_semanal_protocolos"

_CACHE_TTL = 3600
_FILTERS_CACHE_KEY = "pic:monitoring:filters:v2"
_GROUP_CACHE_PREFIX = "pic:monitoring:group:v1:"
_MOTIVOS_CACHE_PREFIX = "pic:monitoring:motivos:v1:"
_SERIES_CACHE_PREFIX = "pic:monitoring:series:v1:"
_PROTOCOLS_CACHE_PREFIX = "pic:monitoring:protocols:v2:"
_LATEST_WEEK_CACHE_PREFIX = "pic:monitoring:latest_week:v1:"

_MAX_ROWS_GUARD = 1000

_MESES_PT = [
    "Jan",
    "Fev",
    "Mar",
    "Abr",
    "Mai",
    "Jun",
    "Jul",
    "Ago",
    "Set",
    "Out",
    "Nov",
    "Dez",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _to_int(value: Any) -> int:
    """Coerce sum() do PostgREST (numérico JSON pode vir int/float/str)."""
    if value is None or value == "":
        return 0
    return int(float(value))


def _to_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _filters_payload(filters: MonitoringFilters) -> dict[str, Any]:
    return {
        "grupo": sorted(filters.grupo) if filters.grupo else None,
        "cohort": sorted(filters.cohort) if filters.cohort else None,
        "status": sorted(filters.status) if filters.status else None,
        "has_bolsa_familia": filters.has_bolsa_familia,
        "camada": filters.camada,
        # Ordenada: mesma seleção em ordem diferente não gera cache duplicado.
        "regiao": sorted(filters.regiao) if filters.regiao else None,
    }


def _hash_payload(payload: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str).encode()
    ).hexdigest()


def _make_group_key(user_id: str | None, filters: MonitoringFilters) -> str:
    return _GROUP_CACHE_PREFIX + _hash_payload(
        {"user_id": user_id, "filters": _filters_payload(filters)}
    )


def _make_motivos_key(
    user_id: str | None, latest_week: str, filters: MonitoringFilters
) -> str:
    return _MOTIVOS_CACHE_PREFIX + _hash_payload(
        {"user_id": user_id, "week": latest_week, "filters": _filters_payload(filters)}
    )


def _make_series_key(
    user_id: str | None, protocolo_id: str, filters: MonitoringFilters
) -> str:
    return _SERIES_CACHE_PREFIX + _hash_payload(
        {
            "user_id": user_id,
            "protocolo_id": protocolo_id,
            "filters": _filters_payload(filters),
        }
    )


def _make_protocols_key(
    user_id: str | None,
    week_start: str,
    secretaria: str | None,
    filters: MonitoringFilters,
) -> str:
    return _PROTOCOLS_CACHE_PREFIX + _hash_payload(
        {
            "user_id": user_id,
            "week": week_start,
            "secretaria": secretaria,
            "filters": _filters_payload(filters),
        }
    )


def _make_latest_week_key(user_id: str | None, filters: MonitoringFilters) -> str:
    return _LATEST_WEEK_CACHE_PREFIX + _hash_payload(
        {"user_id": user_id, "filters": _filters_payload(filters)}
    )


def _apply_filters(query: Any, filters: MonitoringFilters) -> Any:
    """Filtros compartilhados (mapeamento da seção 5.4 do documento).

    Múltiplas regiões viram ``in`` (OR): o multiselect do mapa soma as
    regiões selecionadas numa única série.
    """
    if filters.grupo:
        query = query.in_("pic_grupo", filters.grupo)
    if filters.cohort:
        query = query.in_("pic_cohort", filters.cohort)
    if filters.status:
        query = query.in_("pic_status", filters.status)
    if filters.has_bolsa_familia is not None:
        query = query.eq("has_bolsa_familia", filters.has_bolsa_familia)
    if filters.camada and filters.regiao:
        column = CAMADA_COLUMN.get(filters.camada)
        if column is None:
            raise ValueError(f"Camada territorial desconhecida: {filters.camada!r}")
        query = query.in_(column, filters.regiao)
    return query


def _cohort_label(iso: str) -> str:
    """'2025-03-01' → 'Mar/2025' (abreviação pt-BR, sem depender de locale)."""
    try:
        year, month, _day = iso.split("-")
        return f"{_MESES_PT[int(month) - 1]}/{year}"
    except (ValueError, IndexError):
        return iso


class PostgrestMonitoringRepository(IMonitoringRepository):
    def __init__(self, client: Any, redis_client: Any = None) -> None:
        self._client = client
        self._redis = redis_client

    # ------------------------------------------------------------------
    # Redis helpers (genéricos)
    # ------------------------------------------------------------------

    async def _get_json(self, key: str, what: str) -> Any | None:
        if self._redis is None:
            return None
        try:
            raw = await self._redis.get(key)
            if raw is None:
                return None
            # HIT é o caminho quente (uma linha de log por requisição em
            # produção vira ruído) — fica em debug.
            logger.debug(f"[monitoring] {what} cache HIT")
            return json.loads(raw)
        except Exception as exc:
            logger.warning(f"[monitoring] {what} cache read error (ignoring): {exc}")
            return None

    async def _set_json(self, key: str, payload: Any, what: str) -> None:
        if self._redis is None:
            return
        try:
            await self._redis.set(key, json.dumps(payload, default=str), ex=_CACHE_TTL)
            logger.info(f"[monitoring] {what} cache SET (TTL {_CACHE_TTL}s)")
        except Exception as exc:
            logger.warning(f"[monitoring] {what} cache write error (ignoring): {exc}")

    # ------------------------------------------------------------------
    # IMonitoringRepository
    # ------------------------------------------------------------------

    async def fetch_filter_options(
        self,
        user_token: str | None = None,
        bypass_cache: bool = False,
    ) -> MonitoringFilterOptions:
        if not bypass_cache:
            cached = await self._get_json(_FILTERS_CACHE_KEY, "filters")
            if cached is not None:
                return MonitoringFilterOptions.model_validate(cached)

        async with self._client.with_user_token(user_token):
            latest = await self._query_latest_week_raw(MonitoringFilters())
            if latest is None:
                await self._set_json(_FILTERS_CACHE_KEY, {}, "filters")
                return MonitoringFilterOptions()

            select_count = "{col},qtd:participante_quantidade.sum()"
            grupos_q = self._client.table(_TABLE).select(
                select_count.format(col="pic_grupo")
            )
            grupos_q = grupos_q.not_.is_("pic_grupo", "null")
            grupos_q = grupos_q.eq("protocolo_id", PROTOCOLO_TOTAL)
            grupos_q = grupos_q.eq("data_referencia_semana_inicio", latest)

            cohorts_q = self._client.table(_TABLE).select(
                select_count.format(col="pic_cohort")
            )
            cohorts_q = cohorts_q.not_.is_("pic_cohort", "null")
            cohorts_q = cohorts_q.eq("protocolo_id", PROTOCOLO_TOTAL)
            cohorts_q = cohorts_q.eq("data_referencia_semana_inicio", latest)

            status_q = self._client.table(_TABLE).select(
                select_count.format(col="pic_status")
            )
            status_q = status_q.not_.is_("pic_status", "null")
            status_q = status_q.eq("protocolo_id", PROTOCOLO_TOTAL)
            status_q = status_q.eq("data_referencia_semana_inicio", latest)

            protocolos_q = self._client.table(_TABLE).select(
                "protocolo_id,protocolo_descricao,protocolo_secretaria,"
                "n:protocolo_id.count()"
            )
            protocolos_q = protocolos_q.eq("data_referencia_semana_inicio", latest)

            (
                grupos_resp,
                cohorts_resp,
                status_resp,
                protocolos_resp,
            ) = await asyncio.gather(
                grupos_q.execute(),
                cohorts_q.execute(),
                status_q.execute(),
                protocolos_q.execute(),
            )

        grupos = sorted(
            (
                MonitoringOption(
                    value=row["pic_grupo"],
                    label=row["pic_grupo"],
                    count=_to_int(row.get("qtd")),
                )
                for row in grupos_resp.data or []
            ),
            key=lambda o: (o.count or 0),
            reverse=True,
        )
        cohorts = sorted(
            (
                MonitoringOption(
                    value=row["pic_cohort"],
                    label=_cohort_label(row["pic_cohort"]),
                    count=_to_int(row.get("qtd")),
                )
                for row in cohorts_resp.data or []
            ),
            key=lambda o: o.value,
        )
        status_opts = sorted(
            (
                MonitoringOption(
                    value=row["pic_status"],
                    label=row["pic_status"],
                    count=_to_int(row.get("qtd")),
                )
                for row in status_resp.data or []
            ),
            key=lambda o: o.value,
        )
        protocolos = [
            ProtocolOption(
                id=row["protocolo_id"],
                descricao=row.get("protocolo_descricao"),
                secretaria=row.get("protocolo_secretaria"),
            )
            for row in protocolos_resp.data or []
            if row.get("protocolo_id") != NIVEL_GERAL
        ]
        protocolos.sort(key=lambda p: (p.secretaria or "", p.descricao or ""))
        secretarias = sorted({p.secretaria for p in protocolos if p.secretaria})

        options = MonitoringFilterOptions(
            grupos=grupos,
            cohorts=cohorts,
            status=status_opts,
            protocolos=protocolos,
            secretarias=secretarias,
        )
        await self._set_json(
            _FILTERS_CACHE_KEY, options.model_dump(mode="json"), "filters"
        )
        logger.info(
            f"[monitoring] filter options: {len(grupos)} grupos, "
            f"{len(cohorts)} cohorts, {len(status_opts)} status, "
            f"{len(protocolos)} protocolos (semana {latest})"
        )
        return options

    async def fetch_group_series(
        self,
        filters: MonitoringFilters,
        user_token: str | None = None,
        user_id: str | None = None,
        bypass_cache: bool = False,
    ) -> list[GroupWeekRow]:
        cache_key = _make_group_key(user_id, filters)
        if not bypass_cache:
            cached = await self._get_json(cache_key, "group")
            if cached is not None:
                return [GroupWeekRow.model_validate(r) for r in cached]

        async with self._client.with_user_token(user_token):
            query = self._client.table(_TABLE).select(
                "data_referencia_semana_inicio,data_referencia_semanal,"
                "pic_status,qtd:participante_quantidade.sum()"
            )
            query = query.eq("protocolo_id", PROTOCOLO_TOTAL)
            query = _apply_filters(query, filters)
            query = query.order("data_referencia_semana_inicio")
            resp = await query.execute()

        rows = self._guard_rows(resp.data, "group")
        series = [
            GroupWeekRow(
                week_start=row["data_referencia_semana_inicio"],
                snapshot_date=_to_str(row.get("data_referencia_semanal")),
                status=row["pic_status"],
                qtd=_to_int(row.get("qtd")),
            )
            for row in rows
        ]
        await self._set_json(
            cache_key, [s.model_dump(mode="json") for s in series], "group"
        )
        logger.info(
            f"[monitoring] group series: {len(series)} linhas "
            f"user_id={user_id!r} filtros={_filters_payload(filters)}"
        )
        return series

    async def fetch_motivos(
        self,
        latest_week: str,
        filters: MonitoringFilters,
        user_token: str | None = None,
        user_id: str | None = None,
        bypass_cache: bool = False,
    ) -> list[MotivoInativoRow]:
        cache_key = _make_motivos_key(user_id, latest_week, filters)
        if not bypass_cache:
            cached = await self._get_json(cache_key, "motivos")
            if cached is not None:
                return [MotivoInativoRow.model_validate(r) for r in cached]

        async with self._client.with_user_token(user_token):
            query = self._client.table(_TABLE).select(
                "pic_status_inativo_motivo,qtd:participante_quantidade.sum()"
            )
            query = query.eq("protocolo_id", PROTOCOLO_TOTAL)
            query = query.eq("pic_status", "Inativo")
            query = query.eq("data_referencia_semana_inicio", latest_week)
            query = _apply_filters(query, filters)
            resp = await query.execute()

        rows = self._guard_rows(resp.data, "motivos")
        motivos = [
            MotivoInativoRow(
                motivo=_to_str(row.get("pic_status_inativo_motivo")),
                qtd=_to_int(row.get("qtd")),
            )
            for row in rows
        ]
        # Ordena por quantidade desc (maiores motivos primeiro)
        motivos.sort(key=lambda m: m.qtd, reverse=True)
        await self._set_json(
            cache_key, [m.model_dump(mode="json") for m in motivos], "motivos"
        )
        logger.info(
            f"[monitoring] motivos semana {latest_week}: {len(motivos)} "
            f"user_id={user_id!r}"
        )
        return motivos

    async def fetch_protocol_series(
        self,
        protocolo_id: str,
        filters: MonitoringFilters,
        user_token: str | None = None,
        user_id: str | None = None,
        bypass_cache: bool = False,
    ) -> list[ProtocolWeekRow]:
        cache_key = _make_series_key(user_id, protocolo_id, filters)
        if not bypass_cache:
            cached = await self._get_json(cache_key, "series")
            if cached is not None:
                return [ProtocolWeekRow.model_validate(r) for r in cached]

        async with self._client.with_user_token(user_token):
            query = self._client.table(_TABLE).select(
                "data_referencia_semana_inicio,data_referencia_semanal,"
                "pic_status,protocolo_descricao,protocolo_secretaria,"
                "qtd:participante_quantidade.sum(),"
                "regular:participante_regular_quantidade.sum(),"
                "atencao:participante_atencao_quantidade.sum(),"
                "nao_priorizado:participante_nao_priorizado_quantidade.sum(),"
                "irregular:participante_irregular_quantidade.sum(),"
                "outros:participante_outros_quantidade.sum(),"
                "nao_aplica:participante_nao_aplica_quantidade.sum()"
            )
            query = query.eq("protocolo_id", protocolo_id)
            if protocolo_id == NIVEL_GERAL:
                # Regularidade geral: linhas ``nivel='geral'`` (o número
                # geral consolidado — participante regular em todos os
                # protocolos aplicáveis), identificadas também por
                # protocolo_id/protocolo_secretaria = 'geral'.
                query = query.eq("nivel", NIVEL_GERAL)
                query = query.eq("protocolo_secretaria", NIVEL_GERAL)
            query = _apply_filters(query, filters)
            query = query.order("data_referencia_semana_inicio")
            resp = await query.execute()

        rows = self._guard_rows(resp.data, "series")
        series = [
            ProtocolWeekRow(
                week_start=row["data_referencia_semana_inicio"],
                snapshot_date=_to_str(row.get("data_referencia_semanal")),
                status=row["pic_status"],
                protocolo_descricao=row.get("protocolo_descricao"),
                protocolo_secretaria=row.get("protocolo_secretaria"),
                qtd=_to_int(row.get("qtd")),
                regular=_to_int(row.get("regular")),
                atencao=_to_int(row.get("atencao")),
                nao_priorizado=_to_int(row.get("nao_priorizado")),
                irregular=_to_int(row.get("irregular")),
                outros=_to_int(row.get("outros")),
                nao_aplica=_to_int(row.get("nao_aplica")),
            )
            for row in rows
        ]
        await self._set_json(
            cache_key, [s.model_dump(mode="json") for s in series], "series"
        )
        logger.info(
            f"[monitoring] protocol series {protocolo_id!r}: {len(series)} "
            f"linhas user_id={user_id!r}"
        )
        return series

    async def fetch_protocols_summary(
        self,
        week_start: str,
        secretaria: str | None,
        filters: MonitoringFilters,
        user_token: str | None = None,
        user_id: str | None = None,
        bypass_cache: bool = False,
    ) -> list[ProtocolWeekSummaryRow]:
        cache_key = _make_protocols_key(user_id, week_start, secretaria, filters)
        if not bypass_cache:
            cached = await self._get_json(cache_key, "protocols")
            if cached is not None:
                return [ProtocolWeekSummaryRow.model_validate(r) for r in cached]

        async with self._client.with_user_token(user_token):
            query = self._client.table(_TABLE).select(
                "data_referencia_semanal,protocolo_id,protocolo_descricao,"
                "protocolo_secretaria,qtd:participante_quantidade.sum(),"
                "regular:participante_regular_quantidade.sum(),"
                "atencao:participante_atencao_quantidade.sum(),"
                "irregular:participante_irregular_quantidade.sum(),"
                "nao_aplica:participante_nao_aplica_quantidade.sum()"
            )
            query = query.eq("data_referencia_semana_inicio", week_start)
            if secretaria:
                query = query.eq("protocolo_secretaria", secretaria)
            query = _apply_filters(query, filters)
            resp = await query.execute()

        rows = self._guard_rows(resp.data, "protocols")
        summary = [
            ProtocolWeekSummaryRow(
                protocolo_id=row["protocolo_id"],
                protocolo_descricao=row.get("protocolo_descricao"),
                protocolo_secretaria=row.get("protocolo_secretaria"),
                snapshot_date=_to_str(row.get("data_referencia_semanal")),
                qtd=_to_int(row.get("qtd")),
                regular=_to_int(row.get("regular")),
                atencao=_to_int(row.get("atencao")),
                irregular=_to_int(row.get("irregular")),
                nao_aplica=_to_int(row.get("nao_aplica")),
            )
            for row in rows
            if row.get("protocolo_id") != NIVEL_GERAL
        ]
        summary.sort(
            key=lambda r: (r.protocolo_secretaria or "", r.protocolo_descricao or "")
        )
        await self._set_json(
            cache_key, [s.model_dump(mode="json") for s in summary], "protocols"
        )
        logger.info(
            f"[monitoring] protocols semana {week_start}"
            f"{' secretaria=' + secretaria if secretaria else ''}: "
            f"{len(summary)} user_id={user_id!r}"
        )
        return summary

    async def fetch_latest_week(
        self,
        filters: MonitoringFilters,
        user_token: str | None = None,
        user_id: str | None = None,
        bypass_cache: bool = False,
    ) -> str | None:
        cache_key = _make_latest_week_key(user_id, filters)
        if not bypass_cache:
            cached = await self._get_json(cache_key, "latest_week")
            if cached is not None:
                return cached

        async with self._client.with_user_token(user_token):
            latest = await self._query_latest_week_raw(filters)

        await self._set_json(cache_key, latest, "latest_week")
        return latest

    # ------------------------------------------------------------------
    # Internos
    # ------------------------------------------------------------------

    async def _query_latest_week_raw(self, filters: MonitoringFilters) -> str | None:
        """Semana mais recente com dados (âncora) — sem cache próprio."""
        query = self._client.table(_TABLE).select("data_referencia_semana_inicio")
        query = query.eq("protocolo_id", PROTOCOLO_TOTAL)
        query = _apply_filters(query, filters)
        query = query.order("data_referencia_semana_inicio", desc=True).limit(1)
        resp = await query.execute()
        rows = resp.data or []
        if not rows:
            return None
        return _to_str(rows[0].get("data_referencia_semana_inicio"))

    def _guard_rows(self, rows: Any, what: str) -> list[dict]:
        data = rows or []
        if len(data) >= _MAX_ROWS_GUARD:
            logger.warning(
                f"[monitoring] {what}: resposta com {len(data)} linhas "
                f"(>= {_MAX_ROWS_GUARD}) — possível truncamento do PostgREST"
            )
        return data
