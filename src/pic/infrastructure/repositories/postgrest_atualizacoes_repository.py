"""PostgREST implementation of IAtualizacoesRepository.

Fonte: ``endpoint_participante_visao_geral_semanal_protocolos`` (agregada por
protocolo/semana, particionada por ``data_referencia_semana_inicio``).

Design notes (mesmo padrão do ``postgrest_monitoring_repository.py``):

- Todas as consultas rodam dentro de ``with_user_token`` — a RLS das colunas
  de unidade é aplicada ANTES das agregações, então contagens e porcentagens
  são do mesmo escopo que o usuário vê.
- Cache Redis **por usuário** (TTL 15 min — doc §6): um agregado de super
  admin não pode ser servido para usuário restrito. Chave por consulta:
  ``pic:atualizacoes:<q>:v1:<hash(user, camada, regiao, semanas)>``.
- Agregações do PostgREST: colunas não agregadas no ``select`` viram chaves
  do GROUP BY implícito.
- Guarda defensiva de linhas (limite de 1000 do PostgREST) com log.
"""

import hashlib
import json
from typing import Any

from src.pic.application.ports.atualizacoes_repository import (
    IAtualizacoesRepository,
)
from src.pic.domain.models.atualizacoes import (
    FocoRow,
    ProtocoloSemanaRow,
    SemanaStatusRow,
)
from src.pic.domain.models.territorio import CAMADA_COLUMN
from src.utils.log import logger

_TABLE = "endpoint_participante_visao_geral_semanal_protocolos"

# Doc §6: cache Redis por usuário, TTL 15 min.
_CACHE_TTL = 900
_CACHE_PREFIX = "pic:atualizacoes:v1:"

_MAX_ROWS_GUARD = 1000

# Camadas cujo RAW é código: o rótulo vem da própria tabela semanal (decisão
# Q6 — o nome como definido na tabela; nada de GeoJSON no painel).
_CAMADA_LABEL_COLUMN: dict[str, str] = {
    "cas": "nome_cas",
    "cre": "nome_cre",
    "ap": "nome_ap",
}


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


def _hash_payload(payload: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str).encode()
    ).hexdigest()


def _make_cache_key(
    tag: str,
    user_id: str | None,
    camada: str,
    regiao: str,
    payload: dict[str, Any],
) -> str:
    return (
        _CACHE_PREFIX
        + tag
        + ":"
        + _hash_payload(
            {
                "user_id": user_id,
                "camada": camada,
                "regiao": regiao,
                "params": payload,
            }
        )
    )


def _camada_column(camada: str) -> str:
    column = CAMADA_COLUMN.get(camada)
    if column is None:
        raise ValueError(f"Camada territorial desconhecida: {camada!r}")
    return column


def _base_query(
    client: Any, camada: str | None, regiao: str | None, select: str
) -> Any:
    """Consulta base da tabela semanal: select + recorte territorial (eq).

    ``regiao=None`` → sem recorte: o escopo vem da RLS do token (painel segue
    os acessos do usuário).
    """
    query = client.table(_TABLE).select(select)
    if regiao is not None:
        query = query.eq(_camada_column(camada), regiao)
    return query


class PostgrestAtualizacoesRepository(IAtualizacoesRepository):
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
            # HIT é o caminho quente — fica em debug (evita ruído em prod).
            logger.debug(f"[atualizacoes] {what} cache HIT")
            return json.loads(raw)
        except Exception as exc:
            logger.warning(f"[atualizacoes] {what} cache read error (ignoring): {exc}")
            return None

    async def _set_json(self, key: str, payload: Any, what: str) -> None:
        if self._redis is None:
            return
        try:
            await self._redis.set(key, json.dumps(payload, default=str), ex=_CACHE_TTL)
            logger.debug(f"[atualizacoes] {what} cache SET (TTL {_CACHE_TTL}s)")
        except Exception as exc:
            logger.warning(f"[atualizacoes] {what} cache write error (ignoring): {exc}")

    # ------------------------------------------------------------------
    # IAtualizacoesRepository
    # ------------------------------------------------------------------

    async def fetch_semanas_status(
        self,
        camada: str | None,
        regiao: str | None,
        semanas: list[str],
        user_token: str | None = None,
        user_id: str | None = None,
        bypass_cache: bool = False,
    ) -> list[SemanaStatusRow]:
        """Q1 — base + regularidade + série (5 semanas) — §6 da doc."""
        cache_key = _make_cache_key("q1", user_id, camada, regiao, {"semanas": semanas})
        if not bypass_cache:
            cached = await self._get_json(cache_key, "q1")
            if cached is not None:
                return [SemanaStatusRow.model_validate(r) for r in cached]

        async with self._client.with_user_token(user_token):
            label_col = _CAMADA_LABEL_COLUMN.get(camada)
            select = (
                "data_referencia_semana_inicio,pic_status,"
                "qtd:participante_quantidade.sum(),"
                "regular:participante_regular_quantidade.sum(),"
                "atencao:participante_atencao_quantidade.sum(),"
                "irregular:participante_irregular_quantidade.sum()"
            )
            if label_col:
                # Rótulo da região (constante por região — não multiplica
                # linhas no GROUP BY implícito).
                select = f"{label_col},{select}"
            query = _base_query(self._client, camada, regiao, select)
            query = query.eq("nivel", "geral")
            query = query.eq("protocolo_secretaria", "geral")
            query = query.in_("data_referencia_semana_inicio", semanas)
            query = query.order("data_referencia_semana_inicio")
            resp = await query.execute()

        rows = self._guard_rows(resp.data, "q1")
        label_col = _CAMADA_LABEL_COLUMN.get(camada)
        result = [
            SemanaStatusRow(
                week_start=str(row["data_referencia_semana_inicio"]),
                status=str(row["pic_status"]),
                qtd=_to_int(row.get("qtd")),
                regular=_to_int(row.get("regular")),
                atencao=_to_int(row.get("atencao")),
                irregular=_to_int(row.get("irregular")),
                regiao_label=(_to_str(row.get(label_col)) if label_col else None),
            )
            for row in rows
        ]
        await self._set_json(
            cache_key, [r.model_dump(mode="json") for r in result], "q1"
        )
        logger.info(
            f"[atualizacoes] q1: {len(result)} linhas user_id={user_id!r} "
            f"camada={camada!r} regiao={regiao!r}"
        )
        return result

    async def fetch_protocolos(
        self,
        camada: str | None,
        regiao: str | None,
        semanas: list[str],
        secretarias: list[str] | None = None,
        user_token: str | None = None,
        user_id: str | None = None,
        bypass_cache: bool = False,
    ) -> list[ProtocoloSemanaRow]:
        """Q2 — extremos por protocolo (W−(N+1) e W−1) — §6 da doc.

        ``secretarias`` filtra ``protocolo_secretaria`` (RLS recorta unidade,
        não secretaria): ``None`` = sem filtro; ``[]`` = sem acesso a
        protocolos (retorna vazio sem consultar); lista = ``in_(...)``.
        O filtro entra na cache key — acesso revogado não reaproveita
        resultado antigo dentro do TTL.
        """
        cache_key = _make_cache_key(
            "q2",
            user_id,
            camada,
            regiao,
            {"semanas": semanas, "secretarias": secretarias},
        )
        if not bypass_cache:
            cached = await self._get_json(cache_key, "q2")
            if cached is not None:
                return [ProtocoloSemanaRow.model_validate(r) for r in cached]

        if secretarias is not None and not secretarias:
            # Sem acesso a nenhum protocolo — card fica vazio, sem consulta.
            logger.info(
                f"[atualizacoes] q2: sem acesso a protocolos user_id={user_id!r}"
            )
            return []

        async with self._client.with_user_token(user_token):
            query = _base_query(
                self._client,
                camada,
                regiao,
                "data_referencia_semana_inicio,protocolo_id,protocolo_descricao,"
                "qtd:participante_quantidade.sum(),"
                "regular:participante_regular_quantidade.sum(),"
                "atencao:participante_atencao_quantidade.sum()",
            )
            query = query.neq("nivel", "geral")
            # Taxa de regularidade dos ATIVOS (linhas Inativo também trazem
            # regular/irregular — V1, §7) — exclui da soma.
            query = query.eq("pic_status", "Ativo")
            if secretarias is not None:
                # RLS recorta unidade, não secretaria — o filtro de protocolo
                # por secretaria é responsabilidade do backend.
                query = query.in_("protocolo_secretaria", secretarias)
            query = query.in_("data_referencia_semana_inicio", semanas)
            query = query.order("data_referencia_semana_inicio")
            resp = await query.execute()

        rows = self._guard_rows(resp.data, "q2")
        result = [
            ProtocoloSemanaRow(
                week_start=str(row["data_referencia_semana_inicio"]),
                protocolo_id=str(row["protocolo_id"]),
                protocolo_descricao=_to_str(row.get("protocolo_descricao")),
                qtd=_to_int(row.get("qtd")),
                regular=_to_int(row.get("regular")),
                atencao=_to_int(row.get("atencao")),
            )
            for row in rows
        ]
        await self._set_json(
            cache_key, [r.model_dump(mode="json") for r in result], "q2"
        )
        logger.info(
            f"[atualizacoes] q2: {len(result)} linhas user_id={user_id!r} "
            f"camada={camada!r} regiao={regiao!r}"
        )
        return result

    async def fetch_foco(
        self,
        camada: str | None,
        regiao: str | None,
        sub_camada: str,
        semanas: list[str],
        user_token: str | None = None,
        user_id: str | None = None,
        bypass_cache: bool = False,
    ) -> list[FocoRow]:
        """Q3 — foco (group by sub-camada nas semanas pedidas) — §6 da doc.

        ``semanas`` = [W−(N+1), W−1] (ou só [W−1] sem comparativo): o estoque
        escolhe o local e o delta acompanha a janela do seletor.
        """
        cache_key = _make_cache_key(
            "q3", user_id, camada, regiao, {"sub_camada": sub_camada, "semanas": semanas}
        )
        if not bypass_cache:
            cached = await self._get_json(cache_key, "q3")
            if cached is not None:
                return [FocoRow.model_validate(r) for r in cached]

        async with self._client.with_user_token(user_token):
            query = _base_query(
                self._client,
                camada,
                regiao,
                f"data_referencia_semana_inicio,{sub_camada},"
                "irregular:participante_irregular_quantidade.sum()",
            )
            query = query.eq("nivel", "geral")
            # Mesmo escopo da Q1: linhas do número geral consolidado — o
            # total de irregulares da região (Q1) tem que fechar com o foco.
            # Só Ativos (linhas Inativo também têm irregular — V1, §7).
            query = query.eq("protocolo_secretaria", "geral")
            query = query.eq("pic_status", "Ativo")
            query = query.in_("data_referencia_semana_inicio", semanas)
            query = query.not_.is_(sub_camada, "null")
            # Sem order/limit: o PostgREST não ordena por alias agregado
            # (42703) — o máximo é escolhido no use case (≤ 167 linhas ×
            # semanas).
            resp = await query.execute()

        rows = self._guard_rows(resp.data, "q3")
        result = [
            FocoRow(
                week_start=str(row["data_referencia_semana_inicio"]),
                local=str(row[sub_camada]),
                irregular=_to_int(row.get("irregular")),
            )
            for row in rows
        ]
        await self._set_json(
            cache_key, [r.model_dump(mode="json") for r in result], "q3"
        )
        logger.info(
            f"[atualizacoes] q3: {len(result)} linhas user_id={user_id!r} "
            f"sub_camada={sub_camada!r}"
        )
        return result

    # ------------------------------------------------------------------
    # Internos
    # ------------------------------------------------------------------

    def _guard_rows(self, rows: Any, what: str) -> list[dict]:
        data = rows or []
        if len(data) >= _MAX_ROWS_GUARD:
            logger.warning(
                f"[atualizacoes] {what}: resposta com {len(data)} linhas "
                f"(>= {_MAX_ROWS_GUARD}) — possível truncamento do PostgREST"
            )
        return data
