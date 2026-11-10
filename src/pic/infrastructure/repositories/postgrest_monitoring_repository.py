"""PostgREST implementation of IMonitoringRepository.

Fonte: ``endpoint_participante_visao_geral_semanal_protocolos`` (agregada por
protocolo/semana, particionada por ``data_referencia_semana_inicio``, janela
móvel de 35 partições).

Design notes:

- Todas as consultas rodam dentro de ``with_user_token`` — a RLS das colunas
  de unidade é aplicada ANTES das agregações, então a série respeita o
  escopo de permissões do usuário.
- Cache Redis: TTL 3600 s; a série é cacheada por ``user_id`` + filtros (a
  resposta varia por RLS).
- Agregações do PostgREST: colunas não agregadas no ``select`` viram chaves
  do GROUP BY implícito — ex.: ``select=week,snapshot,pic_status,
  qtd:participante_quantidade.sum()`` agrega por (week, snapshot, status).
- A resposta fica muito abaixo do limite de 1000 linhas (≤ ~70 linhas), mas
  há guarda defensiva com log.
"""

import hashlib
import json
from typing import Any

from src.pic.application.ports.monitoring_repository import IMonitoringRepository
from src.pic.domain.models.monitoring import (
    NIVEL_GERAL,
    MonitoringFilters,
    ProtocolWeekRow,
)
from src.pic.domain.models.territorio import CAMADA_COLUMN
from src.utils.log import logger

_TABLE = "endpoint_participante_visao_geral_semanal_protocolos"

_CACHE_TTL = 3600
_SERIES_CACHE_PREFIX = "pic:monitoring:series:v1:"

_MAX_ROWS_GUARD = 1000


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
    """Filtros para a chave de cache (ordenados: mesma seleção em outra ordem
    não gera cache duplicado). ``camada`` só entra com ``regiao`` — sem
    região a série é da cidade inteira, qualquer que seja a camada."""
    return {
        "grupo": sorted(filters.grupo) if filters.grupo else None,
        "cohort": sorted(filters.cohort) if filters.cohort else None,
        "status": sorted(filters.status) if filters.status else None,
        "has_bolsa_familia": filters.has_bolsa_familia,
        "camada": filters.camada if filters.regiao else None,
        "regiao": sorted(filters.regiao) if filters.regiao else None,
    }


def _hash_payload(payload: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str).encode()
    ).hexdigest()


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
            logger.debug(f"[monitoring] {what} cache SET (TTL {_CACHE_TTL}s)")
        except Exception as exc:
            logger.warning(f"[monitoring] {what} cache write error (ignoring): {exc}")

    # ------------------------------------------------------------------
    # IMonitoringRepository
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Internos
    # ------------------------------------------------------------------

    def _guard_rows(self, rows: Any, what: str) -> list[dict]:
        data = rows or []
        if len(data) >= _MAX_ROWS_GUARD:
            logger.warning(
                f"[monitoring] {what}: resposta com {len(data)} linhas "
                f"(>= {_MAX_ROWS_GUARD}) — possível truncamento do PostgREST"
            )
        return data
