"""PostgREST implementation of the Acordo de Resultados 2026 repository.

Reuses the pre-aggregated dashboard tables and the wide table to compute the
agreement metrics without any new table. The cohort scope is fixed:
``pic_cohort <= ACORDO_COHORT_CUTOFF`` (``cohort.lte`` on the wide table).

Design notes (mirrors ``postgrest_dashboard_repository.py``):

- All fetches run concurrently with ``asyncio.gather``.
- PostgREST does the aggregations (SUM/GROUP BY); Python only accumulates
  repeated keys and builds the domain objects.
- The data-proxy enforces row-level security server-side when the request
  carries the end-user JWT (``with_user_token``).
- Results are cached in Redis (1800s) keyed by user_id only — the scope is
  fixed, so no filters enter the key. Entries are never shared across users.
"""

import asyncio
import hashlib
import json
import time
from collections import defaultdict
from typing import Any

import httpx
from postgrest import AsyncSelectRequestBuilder
from postgrest.exceptions import APIError

from src.pic.application.ports.acordo_resultados_repository import (
    IAcordoResultadosRepository,
)
from src.pic.domain.models.acordo_resultados import (
    AcordoResultados,
    DistribuicaoPublico,
    StatusResumo,
)
from src.pic.domain.models.dashboard import (
    DistribuicaoMotivoSaida,
    ProtocoloIndicador,
    ResultadoProgramaPoint,
)
from src.pic.infrastructure.dashboard.compute_postgrest import (
    _percentual,
    _percentual_raw,
)
from src.pic.infrastructure.dashboard.config import (
    ACORDO_COHORT_CUTOFF,
    ACORDO_META_REGULARIDADE_PERCENTUAL,
)
from src.pic.infrastructure.dashboard.formatting import _format_mes_label
from src.pic.infrastructure.postgrest_client.client import PostgrestClient
from src.pic.infrastructure.postgrest_client.errors import PostgrestError
from src.pic.infrastructure.repositories.postgrest_dashboard_repository import (
    _CACHE_TTL_SECONDS,
    _apply_filters,
)
from src.utils.log import logger

# ---------------------------------------------------------------------------
# Table names (same data-proxy endpoints used by the dashboard)
# ---------------------------------------------------------------------------
_TABLE_CONSOLIDADO = "endpoint_participante_visao_geral_consolidado"
_TABLE_PROTOCOLOS = "endpoint_participante_visao_geral_protocolos"
_TABLE_SERIES = "endpoint_participante_visao_geral_series"
_TABLE_WIDE = "endpoint_participante_protocolos_wide"

_MAPA_SERIE: dict[str, str] = {
    "geral": "TODOS",
    "smas": "SMAS",
    "sme": "SME",
    "sms": "SMS",
}


def _make_cache_key(user_id: str | None) -> str:
    payload = json.dumps({"user_id": user_id}, sort_keys=True, default=str)
    return "acordo_resultados_v2:" + hashlib.sha256(payload.encode()).hexdigest()


class PostgrestAcordoResultadosRepository(IAcordoResultadosRepository):
    """Agreement metrics read from the data-proxy via PostgREST."""

    def __init__(self, client: PostgrestClient, redis_client: Any = None) -> None:
        self._client = client
        self._redis = redis_client

    async def get_acordo_resultados(
        self,
        user_token: str | None = None,
        user_id: str | None = None,
        bypass_cache: bool = False,
    ) -> AcordoResultados:
        start = time.perf_counter()

        cache_key = _make_cache_key(user_id)
        if not bypass_cache and self._redis is not None:
            cached = await self._get_from_cache(cache_key)
            if cached is not None:
                logger.info(
                    f"[acordo] cache HIT ({time.perf_counter() - start:.3f}s)"
                )
                return cached

        logger.info("[acordo] ── CACHE MISS — iniciando queries paralelas ──────────────")
        fetch_start = time.perf_counter()
        async with self._client.with_user_token(user_token):
            (
                totais,
                motivos,
                grupos,
                ras,
                cartao_pic,
                bolsa_familia,
                protocolos,
                series,
                racas,
            ) = await asyncio.gather(
                self._fetch_totais_por_status(),
                self._fetch_motivos(),
                self._fetch_grupos(),
                self._fetch_ras(),
                self._fetch_cartao_pic(),
                self._fetch_bolsa_familia(),
                self._fetch_protocolos(),
                self._fetch_series(),
                self._fetch_racas(),
            )
        _fetch_elapsed = (time.perf_counter() - fetch_start) * 1000
        logger.info(f"[acordo] ⏱  TOTAL fetches (paralelo)      : {_fetch_elapsed:7.1f} ms")

        acordo = _calculate_acordo_resultados(
            totais=totais,
            motivos=motivos,
            grupos=grupos,
            ras=ras,
            cartao_pic=cartao_pic,
            bolsa_familia=bolsa_familia,
            protocolos=protocolos,
            series=series,
            racas=racas,
        )

        if self._redis is not None:
            await self._set_cache(cache_key, acordo)

        logger.info(
            f"[acordo] ══ TOTAL repositório               : "
            f"{(time.perf_counter() - start) * 1000:7.1f} ms ══════════════"
        )
        return acordo

    # ------------------------------------------------------------------
    # Fetches (all with the fixed cohort cutoff)
    # ------------------------------------------------------------------

    async def _fetch_totais_por_status(self) -> list[dict[str, Any]]:
        """GROUP BY pic_status: regular/irregular numerators + denominator."""
        _t0 = time.perf_counter()
        try:
            result = await self._execute(
                _apply_filters(
                    self._client.table(_TABLE_CONSOLIDADO).select(
                        "pic_status, "
                        "regular_num:participante_regular_numerador.sum(), "
                        "irregular_num:participante_irregular_numerador.sum(), "
                        "den:participante_regular_denominador.sum()"
                    ),
                    {},
                ).lte("pic_cohort", ACORDO_COHORT_CUTOFF)
            )
        except PostgrestError as exc:
            logger.error(f"[acordo] totais fetch failed: {exc}", exc_info=True)
            raise
        finally:
            _elapsed = time.perf_counter() - _t0
            logger.info(f"[acordo] ⏱  QUERY totais                 : {_elapsed * 1000:7.1f} ms")

        return [
            {
                "status": row.get("pic_status"),
                "regular_num": row.get("regular_num") or 0,
                "irregular_num": row.get("irregular_num") or 0,
                "den": row.get("den") or 0,
            }
            for row in (result.data or [])
        ]

    async def _fetch_motivos(self) -> list[dict[str, Any]]:
        """GROUP BY pic_status_inativo_motivo (inativos apenas)."""
        _t0 = time.perf_counter()
        try:
            query = self._client.table(_TABLE_CONSOLIDADO).select(
                "pic_status_inativo_motivo, "
                "qtd:participante_quantidade.sum()"
            )
            query = query.ilike("pic_status", "inativo")
            result = await self._execute(
                _apply_filters(query, {}).lte("pic_cohort", ACORDO_COHORT_CUTOFF)
            )
        except PostgrestError as exc:
            logger.error(f"[acordo] motivos fetch failed: {exc}", exc_info=True)
            raise
        finally:
            _elapsed = time.perf_counter() - _t0
            logger.info(f"[acordo] ⏱  QUERY motivos                : {_elapsed * 1000:7.1f} ms")

        return [
            {
                "motivo": row.get("pic_status_inativo_motivo"),
                "qtd": row.get("qtd") or 0,
            }
            for row in (result.data or [])
        ]

    async def _fetch_grupos(self) -> list[dict[str, Any]]:
        """GROUP BY pic_grupo."""
        _t0 = time.perf_counter()
        try:
            result = await self._execute(
                _apply_filters(
                    self._client.table(_TABLE_CONSOLIDADO).select(
                        "pic_grupo, qtd:participante_quantidade.sum()"
                    ),
                    {},
                ).lte("pic_cohort", ACORDO_COHORT_CUTOFF)
            )
        except PostgrestError as exc:
            logger.error(f"[acordo] grupos fetch failed: {exc}", exc_info=True)
            raise
        finally:
            _elapsed = time.perf_counter() - _t0
            logger.info(f"[acordo] ⏱  QUERY grupos                 : {_elapsed * 1000:7.1f} ms")

        return [
            {"categoria": row.get("pic_grupo"), "qtd": row.get("qtd") or 0}
            for row in (result.data or [])
        ]

    async def _fetch_ras(self) -> list[dict[str, Any]]:
        """GROUP BY regiao_administrativa na wide table (count)."""
        _t0 = time.perf_counter()
        try:
            result = await self._execute(
                self._client.table(_TABLE_WIDE)
                .select("categoria:regiao_administrativa,total:count()")
                .lte("cohort", ACORDO_COHORT_CUTOFF)
            )
        except PostgrestError as exc:
            logger.error(f"[acordo] ras fetch failed: {exc}", exc_info=True)
            raise
        finally:
            _elapsed = time.perf_counter() - _t0
            logger.info(f"[acordo] ⏱  QUERY ras                    : {_elapsed * 1000:7.1f} ms")

        return [
            {"categoria": row.get("categoria"), "qtd": row.get("total") or 0}
            for row in (result.data or [])
            if row.get("categoria")
        ]

    async def _fetch_cartao_pic(self) -> list[dict[str, Any]]:
        """GROUP BY has_cartao_pic na wide table (count)."""
        _t0 = time.perf_counter()
        try:
            result = await self._execute(
                self._client.table(_TABLE_WIDE)
                .select("has_cartao_pic,count()")
                .lte("cohort", ACORDO_COHORT_CUTOFF)
            )
        except PostgrestError as exc:
            logger.error(f"[acordo] cartao_pic fetch failed: {exc}", exc_info=True)
            raise
        finally:
            _elapsed = time.perf_counter() - _t0
            logger.info(f"[acordo] ⏱  QUERY cartao_pic            : {_elapsed * 1000:7.1f} ms")

        rows = []
        for row in result.data or []:
            valor = row.get("has_cartao_pic")
            if valor is True:
                categoria = "Retirado"
            elif valor is False:
                categoria = "Não retirado"
            else:
                categoria = "Sem direito"
            rows.append({"categoria": categoria, "qtd": row.get("count") or 0})
        return rows

    async def _fetch_bolsa_familia(self) -> list[dict[str, Any]]:
        """GROUP BY has_bolsa_familia no consolidado."""
        _t0 = time.perf_counter()
        try:
            result = await self._execute(
                _apply_filters(
                    self._client.table(_TABLE_CONSOLIDADO).select(
                        "has_bolsa_familia, qtd:participante_quantidade.sum()"
                    ),
                    {},
                ).lte("pic_cohort", ACORDO_COHORT_CUTOFF)
            )
        except PostgrestError as exc:
            logger.error(f"[acordo] bolsa_familia fetch failed: {exc}", exc_info=True)
            raise
        finally:
            _elapsed = time.perf_counter() - _t0
            logger.info(f"[acordo] ⏱  QUERY bolsa_familia         : {_elapsed * 1000:7.1f} ms")

        rows = []
        for row in result.data or []:
            valor = row.get("has_bolsa_familia")
            if valor is True:
                categoria = "Sim"
            elif valor is False:
                categoria = "Não"
            else:
                categoria = "Não informado"
            rows.append({"categoria": categoria, "qtd": row.get("qtd") or 0})
        return rows

    async def _fetch_protocolos(self) -> list[dict[str, Any]]:
        """GROUP BY protocolo_id com numerador/denominador de regularidade."""
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
                    {},
                ).lte("pic_cohort", ACORDO_COHORT_CUTOFF)
            )
        except PostgrestError as exc:
            logger.error(f"[acordo] protocolos fetch failed: {exc}", exc_info=True)
            raise
        finally:
            _elapsed = time.perf_counter() - _t0
            logger.info(f"[acordo] ⏱  QUERY protocolos             : {_elapsed * 1000:7.1f} ms")

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

    async def _fetch_series(self) -> list[dict[str, Any]]:
        """GROUP BY data_referencia_mensal, serie_tipo (evolução mensal)."""
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
                    {},
                ).lte("pic_cohort", ACORDO_COHORT_CUTOFF)
            )
        except PostgrestError as exc:
            logger.error(f"[acordo] series fetch failed: {exc}", exc_info=True)
            raise
        finally:
            _elapsed = time.perf_counter() - _t0
            logger.info(f"[acordo] ⏱  QUERY series                 : {_elapsed * 1000:7.1f} ms")

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

    async def _fetch_racas(self) -> list[dict[str, Any]]:
        """GROUP BY raca na wide table (count)."""
        _t0 = time.perf_counter()
        try:
            result = await self._execute(
                self._client.table(_TABLE_WIDE)
                .select("categoria:raca,total:count()")
                .lte("cohort", ACORDO_COHORT_CUTOFF)
            )
        except PostgrestError as exc:
            logger.error(f"[acordo] racas fetch failed: {exc}", exc_info=True)
            raise
        finally:
            _elapsed = time.perf_counter() - _t0
            logger.info(f"[acordo] ⏱  QUERY racas                  : {_elapsed * 1000:7.1f} ms")

        return [
            {"categoria": row.get("categoria"), "qtd": row.get("total") or 0}
            for row in (result.data or [])
            if row.get("categoria")
        ]

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

    async def _get_from_cache(self, key: str) -> AcordoResultados | None:
        try:
            raw = await self._redis.get(key)
            if raw is None:
                return None
            return AcordoResultados.model_validate(json.loads(raw))
        except Exception as exc:
            logger.warning(f"[acordo] cache read error (ignoring): {exc}")
            return None

    async def _set_cache(self, key: str, acordo: AcordoResultados) -> None:
        try:
            await self._redis.set(
                key, acordo.model_dump_json(), ex=_CACHE_TTL_SECONDS
            )
        except Exception as exc:
            logger.warning(f"[acordo] cache write error (ignoring): {exc}")


# ---------------------------------------------------------------------------
# Pure-Python compute (dados já agregados em SQL)
# ---------------------------------------------------------------------------


def _build_status_resumo(
    rows: list[dict[str, Any]], ativo: bool
) -> StatusResumo:
    regular_num = 0
    irregular_num = 0
    den = 0
    for row in rows:
        status = (row.get("status") or "").lower()
        is_ativo = status == "ativo"
        if is_ativo != ativo:
            continue
        regular_num += int(row.get("regular_num") or 0)
        irregular_num += int(row.get("irregular_num") or 0)
        den += int(row.get("den") or 0)
    return StatusResumo(
        total=den,
        regulares=regular_num,
        irregulares=irregular_num,
        percentual_regular=_percentual(regular_num, den),
        percentual_irregular=_percentual(irregular_num, den),
    )


def _calculate_acordo_resultados(
    *,
    totais: list[dict[str, Any]],
    motivos: list[dict[str, Any]],
    grupos: list[dict[str, Any]],
    ras: list[dict[str, Any]],
    cartao_pic: list[dict[str, Any]],
    bolsa_familia: list[dict[str, Any]],
    protocolos: list[dict[str, Any]],
    series: list[dict[str, Any]],
    racas: list[dict[str, Any]],
) -> AcordoResultados:
    ativos = _build_status_resumo(totais, ativo=True)
    inativos = _build_status_resumo(totais, ativo=False)
    total_participantes = ativos.total + inativos.total

    # --- Protocolos (agrega linhas repetidas por protocolo_id) ------------
    proto_agg: dict[str, dict[str, Any]] = {}
    for row in protocolos:
        pid = row.get("protocolo_id")
        if not pid:
            continue
        if pid not in proto_agg:
            proto_agg[pid] = {
                "descricao": row.get("protocolo_descricao") or "",
                "secretaria": row.get("protocolo_secretaria") or "",
                "num": 0,
                "den": 0,
            }
        else:
            if not proto_agg[pid]["descricao"] and row.get("protocolo_descricao"):
                proto_agg[pid]["descricao"] = row["protocolo_descricao"]
            if not proto_agg[pid]["secretaria"] and row.get("protocolo_secretaria"):
                proto_agg[pid]["secretaria"] = row["protocolo_secretaria"]
        proto_agg[pid]["num"] += row.get("numerador") or 0
        proto_agg[pid]["den"] += row.get("denominador") or 0

    protocolos_lista: list[ProtocoloIndicador] = []
    for pid, dados in proto_agg.items():
        num, den = dados["num"], dados["den"]
        perc_reg_raw = _percentual_raw(num, den)
        protocolos_lista.append(
            ProtocoloIndicador(
                protocolo_id=pid,
                protocolo_descricao=dados["descricao"],
                protocolo_secretaria=dados["secretaria"],
                numerador=num,
                denominador=den,
                percentual_regular=round(perc_reg_raw, 1),
                percentual_irregular=round(100 - perc_reg_raw, 1) if den > 0 else 0.0,
            )
        )
    protocolos_lista.sort(key=lambda p: (p.protocolo_secretaria, p.protocolo_descricao))

    # --- Evolução mensal (% regular por dimensão) -------------------------
    evolucao: dict[str, dict[str, dict[str, int]]] = defaultdict(
        lambda: defaultdict(lambda: {"num": 0, "den": 0})
    )
    for row in series:
        tipo = (row.get("serie_tipo") or "").lower()
        nome_sec = _MAPA_SERIE.get(tipo)
        mes = row.get("mes")
        if not nome_sec or not mes:
            continue
        evolucao[mes][nome_sec]["num"] += row.get("numerador") or 0
        evolucao[mes][nome_sec]["den"] += row.get("denominador") or 0

    evolucao_mensal = [
        ResultadoProgramaPoint(
            mes=mes,
            mes_label=_format_mes_label(mes),
            todos=_percentual(d["TODOS"]["num"], d["TODOS"]["den"]),
            saude=_percentual(d["SMS"]["num"], d["SMS"]["den"]),
            educacao=_percentual(d["SME"]["num"], d["SME"]["den"]),
            assistencia=_percentual(d["SMAS"]["num"], d["SMAS"]["den"]),
        )
        for mes, d in sorted(evolucao.items())
    ]

    # --- Motivos de saída --------------------------------------------------
    motivos_agg: dict[str, int] = {}
    for row in motivos:
        motivo = row.get("motivo")
        if not motivo or not str(motivo).strip():
            motivo = "Não informado"
        else:
            motivo = str(motivo).strip()
        motivos_agg[motivo] = motivos_agg.get(motivo, 0) + int(row.get("qtd") or 0)

    motivos_saida = [
        DistribuicaoMotivoSaida(motivo=m, total=t)
        for m, t in sorted(motivos_agg.items(), key=lambda x: -x[1])
    ]

    # --- Distribuições de público -----------------------------------------
    def _distribuicao(rows: list[dict[str, Any]]) -> list[DistribuicaoPublico]:
        agg: dict[str, int] = {}
        for row in rows:
            categoria = row.get("categoria")
            if not categoria or not str(categoria).strip():
                continue
            categoria = str(categoria).strip()
            agg[categoria] = agg.get(categoria, 0) + int(row.get("qtd") or 0)
        return [
            DistribuicaoPublico(categoria=c, total=t)
            for c, t in sorted(agg.items(), key=lambda x: -x[1])
        ]

    return AcordoResultados(
        total_participantes=total_participantes,
        ativos=ativos,
        inativos=inativos,
        protocolos=protocolos_lista,
        evolucao_mensal=evolucao_mensal,
        motivos_saida=motivos_saida,
        distribuicao_raca=_distribuicao(racas),
        distribuicao_grupo=_distribuicao(grupos),
        distribuicao_ra=_distribuicao(ras),
        distribuicao_cartao_pic=_distribuicao(cartao_pic),
        distribuicao_bolsa_familia=_distribuicao(bolsa_familia),
        meta_regularidade=ACORDO_META_REGULARIDADE_PERCENTUAL,
    )
