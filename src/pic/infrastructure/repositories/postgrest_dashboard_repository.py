"""PostgREST implementation of the dashboard repository.

Replaces the BigQuery/Polars pipeline for GET /api/v2/dashboard. No Polars
anywhere in this module.

Design notes:

- Five tables serve the seven dashboard sections. All share the same filter
  columns, so the same filter-building helper is applied to every query.
- The data-proxy enforces row-level security server-side when the request
  carries the end-user JWT (`with_user_token`). The *secretaria* query param
  does NOT filter rows — it only affects which secretaria bands appear in
  section 6 (tempo médio), exactly as V1 did.
- All five fetches run concurrently with `asyncio.gather` to minimise latency.
- Results are cached in Redis keyed by a deterministic hash of (filters,
  secretaria, user_id). Entries are never shared across users; PostgREST RLS
  scopes each user's data at query time. `bypass_cache=True` skips reading the
  cache but still writes.
- `PGRST_DB_MAX_ROWS` caps each response at 1 000 rows. Sections 1/4/5 use
  PostgREST aggregates (one row back); sections 2/3/6/7 may return up to
  ~hundreds of rows but never approach the cap for this dataset.  If that
  assumption changes, add pagination here.
"""

import asyncio
import hashlib
import json
import time
from typing import Any

import httpx
from postgrest import AsyncSelectRequestBuilder
from postgrest.exceptions import APIError

from src.pic.application.ports.dashboard_repository import IDashboardRepository
from src.pic.domain.models.dashboard import Dashboard
from src.pic.infrastructure.dashboard.compute_postgrest import (
    _calculate_dashboard_metrics_postgrest_v2,
)
from src.pic.infrastructure.dashboard.factory import _create_empty_dashboard
from src.pic.infrastructure.postgrest_client.client import PostgrestClient
from src.pic.infrastructure.postgrest_client.errors import PostgrestError
from src.utils.log import logger

# ---------------------------------------------------------------------------
# Table names
# ---------------------------------------------------------------------------
_TABLE_CONSOLIDADO = "endpoint_participante_visao_geral_consolidado"
_TABLE_PROTOCOLOS = "endpoint_participante_visao_geral_protocolos"
_TABLE_SERIES = "endpoint_participante_visao_geral_series"
_TABLE_TEMPO = "endpoint_participante_visao_geral_tempo_irregular"
_TABLE_RESOLUCAO = "endpoint_participante_visao_geral_resolucao_alertas"

# ---------------------------------------------------------------------------
# Filter helpers (mirrors postgrest_participant_repository conventions)
# ---------------------------------------------------------------------------

# Columns that must match exactly (no ILIKE).  Date columns and unit IDs are
# compared with exact equality; everything else is case-insensitive text.
_EXACT_COLUMNS: frozenset[str] = frozenset({
    "id_cre",
    "id_ap",
    "id_cas",
    "id_cras",
    "id_escola",
    "id_clinica_familia",
    "id_equipe_familia",
    "pic_cohort",
})

_CACHE_TTL_SECONDS = 1800  # 30 minutes (session lifetime)


def _escape_ilike(value: str) -> str:
    """Escape ILIKE wildcards so the value matches literally."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _apply_filters(
    query: AsyncSelectRequestBuilder,
    filters: dict[str, object],
) -> AsyncSelectRequestBuilder:
    """Apply every filter from *filters* to *query*.

    Mirrors the V1 DataManager / postgrest_participant_repository semantics:
    - strings → ilike (case-insensitive exact match)
    - unit-ID / date columns → eq
    - lists → in(...)
    - booleans → is.true / is.false
    """
    for column, raw_value in filters.items():
        if raw_value is None:
            continue

        # Boolean
        if isinstance(raw_value, bool):
            query = query.filter(column, "is", "true" if raw_value else "false")
            continue

        # List (multi-select)
        values: list[Any] = raw_value if isinstance(raw_value, list) else [raw_value]
        values = [v for v in values if v is not None]
        if not values:
            continue

        if column == "has_bolsa_familia":
            bool_val = "true" if values[0] else "false"
            query = query.filter(column, "is", bool_val)
            continue

        if column in _EXACT_COLUMNS:
            if len(values) > 1:
                query = query.filter(
                    column, "in", f"({','.join(str(v) for v in values)})"
                )
            else:
                query = query.eq(column, str(values[0]))
        else:
            if len(values) > 1:
                query = query.filter(
                    column, "in", f"({','.join(str(v) for v in values)})"
                )
            else:
                query = query.ilike(column, _escape_ilike(str(values[0])))

    return query


def _make_cache_key(
    filters: dict[str, object],
    secretaria: str | None,
    user_id: str | None,
) -> str:
    """Deterministic cache key from filters + secretaria + user_id.

    ``user_id`` isolates the cache per user (each user's permission scope is
    enforced by PostgREST RLS at query time), so entries are never shared.
    """
    payload = json.dumps(
        {"filters": filters, "secretaria": secretaria, "user_id": user_id},
        sort_keys=True,
        default=str,
    )
    return "dashboard_v2:" + hashlib.sha256(payload.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Repository
# ---------------------------------------------------------------------------


class PostgrestDashboardRepository(IDashboardRepository):
    """Dashboard metrics read from the data-proxy via PostgREST.

    All five table fetches run concurrently; results are aggregated in pure
    Python (no Polars) by `_calculate_dashboard_metrics_postgrest`.
    """

    def __init__(self, client: PostgrestClient, redis_client: Any = None) -> None:
        self._client = client
        self._redis = redis_client

    # ------------------------------------------------------------------
    # Public interface (IDashboardRepository)
    # ------------------------------------------------------------------

    async def get_dashboard_metrics(
        self,
        filters: dict[str, object],
        user_token: str | None = None,
        secretaria: str | None = None,
        user_id: str | None = None,
        bypass_cache: bool = False,
    ) -> Dashboard:
        """Fetch and compute all seven dashboard sections.

        Args:
            filters: Column-level filters, already mapped from query params.
            user_token: Raw JWT do usuário (access token do Keycloak) repassado
                ao PostgREST via ``with_user_token`` para que o RLS seja aplicado
                corretamente. Segue o mesmo padrão de ``PostgrestParticipantRepository``.
            secretaria: Optional secretaria filter (SMS | SME | SMAS). Does
                NOT filter rows — only controls which bands appear in section 6.
            user_id: Identificador do usuário (CPF) usado para isolar o cache
                por usuário. Sem ele, entradas de cache poderiam vazar entre
                usuários com permissões diferentes.
            bypass_cache: Skip Redis read but still write on cache miss.

        Returns:
            Fully populated `Dashboard` domain object.
        """
        start = time.perf_counter()

        # 1. Try cache -------------------------------------------------------
        cache_key = _make_cache_key(filters, secretaria, user_id)
        if not bypass_cache and self._redis is not None:
            cached = await self._get_from_cache(cache_key)
            if cached is not None:
                logger.info(
                    f"[dashboard] cache HIT ({time.perf_counter() - start:.3f}s)"
                )
                return cached

        # 2. Five concurrent fetches ----------------------------------------
        logger.info("[dashboard] ── CACHE MISS — iniciando 5 queries paralelas ──────────────")
        fetch_start = time.perf_counter()
        async with self._client.with_user_token(user_token):
            (
                consolidado,
                protocolos,
                series,
                tempo,
                resolucao,
            ) = await asyncio.gather(
                self._fetch_consolidado(filters),
                self._fetch_protocolos(filters),
                self._fetch_series(filters),
                self._fetch_tempo(filters),
                self._fetch_resolucao(filters),
            )
        _fetch_elapsed = (time.perf_counter() - fetch_start) * 1000
        logger.info(f"[dashboard] ⏱  TOTAL 5 fetches (paralelo)    : {_fetch_elapsed:7.1f} ms  ← gargalo real = query mais lenta acima")

        # 3. Compute metrics (agregações já feitas em SQL) --------------------
        calc_start = time.perf_counter()
        dashboard = _calculate_dashboard_metrics_postgrest_v2(
            consolidado=consolidado,
            protocolos=protocolos,
            series=series,
            tempo=tempo,
            resolucao=resolucao,
            filtro_secretaria=secretaria,
        )
        _calc_elapsed = (time.perf_counter() - calc_start) * 1000
        logger.info(f"[dashboard] ⏱  COMPUTE métricas Python       : {_calc_elapsed:7.1f} ms")

        # 4. Write cache -------------------------------------------------------
        if self._redis is not None:
            await self._set_cache(cache_key, dashboard)

        _total_elapsed = (time.perf_counter() - start) * 1000
        logger.info(f"[dashboard] ══ TOTAL repositório               : {_total_elapsed:7.1f} ms ══════════════")
        return dashboard

    # ------------------------------------------------------------------
    # Five private fetches (one per table) + consolidado subfetches
    # ------------------------------------------------------------------

    async def _fetch_consolidado_totals(self, filters: dict[str, object]) -> dict[str, int]:
        """Aggregate totals: SUM(numerador/denominador/irregular).
        
        Returns 1 row with sums aggregated by PostgREST.
        """
        _t0 = time.perf_counter()
        try:
            result = await self._execute(
                _apply_filters(
                    self._client.table(_TABLE_CONSOLIDADO).select(
                        "regular_num:participante_regular_numerador.sum(), "
                        "regular_den:participante_regular_denominador.sum(), "
                        "irregular_num:participante_irregular_numerador.sum()"
                    ).limit(1),
                    filters,
                )
            )
        except PostgrestError as exc:
            logger.error(f"[dashboard] consolidado_totals fetch failed: {exc}", exc_info=True)
            raise
        finally:
            _elapsed = time.perf_counter() - _t0
            logger.info(f"[dashboard] ⏱  QUERY consolidado_totals      : {_elapsed * 1000:7.1f} ms")

        row = result.data[0] if result.data else {}
        return {
            "regular_num": row.get("regular_num") or 0,
            "regular_den": row.get("regular_den") or 0,
            "irregular_num": row.get("irregular_num") or 0,
        }

    async def _fetch_consolidado_safras(self, filters: dict[str, object]) -> list[dict[str, Any]]:
        """Aggregate safras: GROUP BY pic_cohort, pic_status.
        
        Returns ~30 rows with SUM(participante_quantidade).
        """
        _t0 = time.perf_counter()
        try:
            result = await self._execute(
                _apply_filters(
                    self._client.table(_TABLE_CONSOLIDADO).select(
                        "pic_cohort, "
                        "pic_status, "
                        "qtd:participante_quantidade.sum()"
                    ),
                    filters,
                )
            )
        except PostgrestError as exc:
            logger.error(f"[dashboard] consolidado_safras fetch failed: {exc}", exc_info=True)
            raise
        finally:
            _elapsed = time.perf_counter() - _t0
            logger.info(f"[dashboard] ⏱  QUERY consolidado_safras      : {_elapsed * 1000:7.1f} ms")

        return [
            {
                "cohort": str(row.get("pic_cohort", "")),
                "status": row.get("pic_status"),
                "qtd": row.get("qtd"),
            }
            for row in (result.data or [])
            if row.get("pic_cohort")
        ]

    async def _fetch_consolidado_motivos(self, filters: dict[str, object]) -> list[dict[str, Any]]:
        """Aggregate motivos: GROUP BY pic_status_inativo_motivo (filtered to inativo).
        
        Returns ~50 rows with SUM(participante_quantidade).
        """
        _t0 = time.perf_counter()
        try:
            query = self._client.table(_TABLE_CONSOLIDADO).select(
                "pic_status_inativo_motivo, "
                "qtd:participante_quantidade.sum()"
            )
            query = query.ilike("pic_status", "inativo")
            result = await self._execute(
                _apply_filters(query, filters)
            )
        except PostgrestError as exc:
            logger.error(f"[dashboard] consolidado_motivos fetch failed: {exc}", exc_info=True)
            raise
        finally:
            _elapsed = time.perf_counter() - _t0
            logger.info(f"[dashboard] ⏱  QUERY consolidado_motivos     : {_elapsed * 1000:7.1f} ms")

        return [
            {
                "motivo": row.get("pic_status_inativo_motivo"),
                "qtd": row.get("qtd"),
            }
            for row in (result.data or [])
        ]

    async def _fetch_consolidado(self, filters: dict[str, object]) -> dict[str, Any]:
        """Orquestra 3 fetches paralelas com agregações SQL.
        
        Returns a dict with three top-level keys:
            totals:  {regular_num, regular_den, irregular_num}
            safras:  [{"cohort": str, "status": str, "qtd": int}]
            motivos: [{"motivo": str | None, "qtd": int}]
        """
        _t0 = time.perf_counter()
        totals, safras, motivos = await asyncio.gather(
            self._fetch_consolidado_totals(filters),
            self._fetch_consolidado_safras(filters),
            self._fetch_consolidado_motivos(filters),
        )
        logger.info(f"[dashboard] ⏱  GRUPO consolidado (3 paralelas)  : {(time.perf_counter() - _t0) * 1000:7.1f} ms")
        return {
            "totals": totals,
            "safras": safras,
            "motivos": motivos,
        }

    async def _fetch_protocolos(
        self, filters: dict[str, object]
    ) -> list[dict[str, Any]]:
        """Section 2 — Protocolos agregados por ID.

        Aggregation: GROUP BY protocolo_id, protocolo_descricao, protocolo_secretaria.
        PostgREST retorna ~50 linhas agregadas (em vez de ~400 brutas).

        Returns:
            [{"protocolo_id", "protocolo_descricao", "protocolo_secretaria",
              "numerador", "denominador"}, ...]
        """
        _t0 = time.perf_counter()
        try:
            result = await self._execute(
                _apply_filters(
                    self._client.table(_TABLE_PROTOCOLOS).select(
                        "protocolo_id, "
                        "protocolo_descricao, "
                        "protocolo_secretaria, "
                        "numerador:protocolo_regular_numerador.sum(), "
                        "denominador:protocolo_regular_denominador.sum()"
                    ).not_.is_("protocolo_id", "null"),
                    filters,
                )
            )
        except PostgrestError as exc:
            logger.error(f"[dashboard] protocolos fetch failed: {exc}", exc_info=True)
            raise
        finally:
            _elapsed = time.perf_counter() - _t0
            logger.info(f"[dashboard] ⏱  QUERY protocolos              : {_elapsed * 1000:7.1f} ms")

        rows = []
        for row in result.data or []:
            pid = row.get("protocolo_id")
            if not pid:
                continue
            rows.append({
                "protocolo_id": pid,
                "protocolo_descricao": row.get("protocolo_descricao") or "",
                "protocolo_secretaria": row.get("protocolo_secretaria") or "",
                "numerador": row.get("numerador") or 0,
                "denominador": row.get("denominador") or 0,
            })
        return rows

    async def _fetch_series(
        self, filters: dict[str, object]
    ) -> list[dict[str, Any]]:
        """Section 3 — Série temporal agregada por tipo e mês.

        Aggregation: GROUP BY data_referencia_mensal, serie_tipo.
        PostgREST retorna ~24 linhas agregadas (em vez de ~200 brutas).
        Python trunca data para mes (YYYY-MM).

        Returns:
            [{"serie_tipo": str, "mes": str (YYYY-MM),
              "numerador": int, "denominador": int}, ...]
        """
        _t0 = time.perf_counter()
        try:
            result = await self._execute(
                _apply_filters(
                    self._client.table(_TABLE_SERIES).select(
                        "serie_tipo, "
                        "data_referencia_mensal, "
                        "numerador:participante_regular_quantidade.sum(), "
                        "denominador:participante_quantidade.sum()"
                    ),
                    filters,
                )
            )
        except PostgrestError as exc:
            logger.error(f"[dashboard] series fetch failed: {exc}", exc_info=True)
            raise
        finally:
            _elapsed = time.perf_counter() - _t0
            logger.info(f"[dashboard] ⏱  QUERY series                  : {_elapsed * 1000:7.1f} ms")

        rows = []
        for row in result.data or []:
            serie_tipo = row.get("serie_tipo")
            data = row.get("data_referencia_mensal")
            if not serie_tipo or not data:
                continue
            mes = str(data)[:7]  # YYYY-MM
            if not mes:
                continue
            rows.append({
                "serie_tipo": serie_tipo,
                "mes": mes,
                "numerador": row.get("numerador") or 0,
                "denominador": row.get("denominador") or 0,
            })
        return rows

    async def _fetch_tempo(self, filters: dict[str, object]) -> dict[str, Any]:
        """Section 6 — Tempo irregular com faixas pré-agregadas por secretaria.

        As colunas de faixa (smas/sme/sms/geral_irregularidade_faixa_*) já vêm
        pré-calculadas no banco. PostgREST aplica SUM() de cada faixa em uma
        única linha retornada — sem aritmética em Python.

        Returns:
            {
                "smas":  {"media": float, "faixa_0_30": int, "faixa_31_60": int,
                          "faixa_61_90": int, "faixa_91_mais": int},
                "sme":   {…},
                "sms":   {…},
                "geral": {"faixa_0_30": int, "faixa_31_60": int,
                          "faixa_61_90": int, "faixa_91_mais": int},
            }
        """
        _t0 = time.perf_counter()
        try:
            result = await self._execute(
                _apply_filters(
                    self._client.table(_TABLE_TEMPO).select(
                        # SMAS
                        "smas_media:smas_duracao_media_valor.avg(), "
                        "smas_faixa_0_30:smas_irregularidade_faixa_0_30.sum(), "
                        "smas_faixa_31_60:smas_irregularidade_faixa_31_60.sum(), "
                        "smas_faixa_61_90:smas_irregularidade_faixa_61_90.sum(), "
                        "smas_faixa_91_mais:smas_irregularidade_faixa_91_mais.sum(), "
                        # SME
                        "sme_media:sme_duracao_media_valor.avg(), "
                        "sme_faixa_0_30:sme_irregularidade_faixa_0_30.sum(), "
                        "sme_faixa_31_60:sme_irregularidade_faixa_31_60.sum(), "
                        "sme_faixa_61_90:sme_irregularidade_faixa_61_90.sum(), "
                        "sme_faixa_91_mais:sme_irregularidade_faixa_91_mais.sum(), "
                        # SMS
                        "sms_media:sms_duracao_media_valor.avg(), "
                        "sms_faixa_0_30:sms_irregularidade_faixa_0_30.sum(), "
                        "sms_faixa_31_60:sms_irregularidade_faixa_31_60.sum(), "
                        "sms_faixa_61_90:sms_irregularidade_faixa_61_90.sum(), "
                        "sms_faixa_91_mais:sms_irregularidade_faixa_91_mais.sum(), "
                        # GERAL (já pré-agregado no banco)
                        "geral_faixa_0_30:geral_irregularidade_faixa_0_30.sum(), "
                        "geral_faixa_31_60:geral_irregularidade_faixa_31_60.sum(), "
                        "geral_faixa_61_90:geral_irregularidade_faixa_61_90.sum(), "
                        "geral_faixa_91_mais:geral_irregularidade_faixa_91_mais.sum()"
                    ).limit(1),
                    filters,
                )
            )
        except PostgrestError as exc:
            logger.error(f"[dashboard] tempo fetch failed: {exc}", exc_info=True)
            raise
        finally:
            _elapsed = time.perf_counter() - _t0
            logger.info(f"[dashboard] ⏱  QUERY tempo                   : {_elapsed * 1000:7.1f} ms")

        row = (result.data or [{}])[0]
        return {
            "smas": {
                "media":          float(row.get("smas_media") or 0.0),
                "faixa_0_30":     int(row.get("smas_faixa_0_30") or 0),
                "faixa_31_60":    int(row.get("smas_faixa_31_60") or 0),
                "faixa_61_90":    int(row.get("smas_faixa_61_90") or 0),
                "faixa_91_mais":  int(row.get("smas_faixa_91_mais") or 0),
            },
            "sme": {
                "media":          float(row.get("sme_media") or 0.0),
                "faixa_0_30":     int(row.get("sme_faixa_0_30") or 0),
                "faixa_31_60":    int(row.get("sme_faixa_31_60") or 0),
                "faixa_61_90":    int(row.get("sme_faixa_61_90") or 0),
                "faixa_91_mais":  int(row.get("sme_faixa_91_mais") or 0),
            },
            "sms": {
                "media":          float(row.get("sms_media") or 0.0),
                "faixa_0_30":     int(row.get("sms_faixa_0_30") or 0),
                "faixa_31_60":    int(row.get("sms_faixa_31_60") or 0),
                "faixa_61_90":    int(row.get("sms_faixa_61_90") or 0),
                "faixa_91_mais":  int(row.get("sms_faixa_91_mais") or 0),
            },
            "geral": {
                "faixa_0_30":     int(row.get("geral_faixa_0_30") or 0),
                "faixa_31_60":    int(row.get("geral_faixa_31_60") or 0),
                "faixa_61_90":    int(row.get("geral_faixa_61_90") or 0),
                "faixa_91_mais":  int(row.get("geral_faixa_91_mais") or 0),
            },
        }

    async def _fetch_resolucao(
        self, filters: dict[str, object]
    ) -> list[dict[str, Any]]:
        """Section 7 — Taxa de resolução agregada por secretaria e mês.

        Aggregation: GROUP BY data_referencia_mensal, secretaria.
        PostgREST retorna ~24 linhas agregadas (em vez de ~100 brutas).
        Python trunca data para mes (YYYY-MM).

        Returns:
            [{"secretaria": str, "mes": str (YYYY-MM),
              "numerador": int, "denominador": int}, ...]
        """
        _t0 = time.perf_counter()
        try:
            result = await self._execute(
                _apply_filters(
                    self._client.table(_TABLE_RESOLUCAO).select(
                        "secretaria, "
                        "data_referencia_mensal, "
                        "numerador:alerta_resolvido_numerador.sum(), "
                        "denominador:alerta_numerador.sum()"
                    ).not_.is_("secretaria", "null"),
                    filters,
                )
            )
        except PostgrestError as exc:
            logger.error(f"[dashboard] resolucao fetch failed: {exc}", exc_info=True)
            raise
        finally:
            _elapsed = time.perf_counter() - _t0
            logger.info(f"[dashboard] ⏱  QUERY resolucao               : {_elapsed * 1000:7.1f} ms")

        rows = []
        for row in result.data or []:
            secretaria = row.get("secretaria")
            data = row.get("data_referencia_mensal")
            if not secretaria or not data:
                continue
            mes = str(data)[:7]
            if not mes:
                continue
            rows.append({
                "secretaria": secretaria,
                "mes": mes,
                "numerador": row.get("numerador") or 0,
                "denominador": row.get("denominador") or 0,
            })
        return rows

    # ------------------------------------------------------------------
    # Execution helper
    # ------------------------------------------------------------------

    async def _execute(self, query: AsyncSelectRequestBuilder):  # type: ignore[return]
        """Execute a PostgREST query, translating errors to PostgrestError."""
        try:
            return await query.execute()
        except APIError as exc:
            raise PostgrestError.from_api_error(exc) from exc
        except httpx.HTTPError as exc:
            raise PostgrestError.from_transport_error(exc) from exc

    # ------------------------------------------------------------------
    # Redis cache helpers
    # ------------------------------------------------------------------

    async def _get_from_cache(self, key: str) -> Dashboard | None:
        _t0 = time.perf_counter()
        try:
            raw = await self._redis.get(key)
            if raw is None:
                logger.info(f"[dashboard] ⏱  CACHE redis GET (miss)      : {(time.perf_counter() - _t0) * 1000:7.1f} ms")
                return None
            _t_deserialize = time.perf_counter()
            data = json.loads(raw)
            result = Dashboard.model_validate(data)
            logger.info(
                f"[dashboard] ⏱  CACHE redis GET            : {(time.perf_counter() - _t0) * 1000:7.1f} ms"
                f"  (network {(_t_deserialize - _t0) * 1000:.1f} ms"
                f" + deserialize {(time.perf_counter() - _t_deserialize) * 1000:.1f} ms)"
                f"  payload {len(raw)} bytes"
            )
            return result
        except Exception as exc:
            logger.warning(f"[dashboard] cache read error (ignoring): {exc}")
            return None

    async def _set_cache(self, key: str, dashboard: Dashboard) -> None:
        _t0 = time.perf_counter()
        try:
            _t_serialize = time.perf_counter()
            raw = dashboard.model_dump_json()
            _t_write = time.perf_counter()
            await self._redis.set(key, raw, ex=_CACHE_TTL_SECONDS)
            logger.info(
                f"[dashboard] ⏱  CACHE redis SET            : {(time.perf_counter() - _t0) * 1000:7.1f} ms"
                f"  (serialize {(_t_write - _t_serialize) * 1000:.1f} ms"
                f" + network {(time.perf_counter() - _t_write) * 1000:.1f} ms)"
                f"  payload {len(raw)} bytes"
            )
        except Exception as exc:
            logger.warning(f"[dashboard] cache write error (ignoring): {exc}")
