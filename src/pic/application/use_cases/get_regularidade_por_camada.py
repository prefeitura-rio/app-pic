"""Use case da regularidade por camada territorial (fase 3 da visualização geográfica).

Orquestra duas fontes:
- agregados por região via PostgREST (RLS aplicada pelo data-proxy) — mesma
  métrica do dashboard: participantes regulares (Regular + Atenção) sobre o
  total de participantes;
- geometrias oficiais da camada: GeoJSONs estáticos commitados
  (``geometrias_estaticas_repository``) para as 5 camadas — bairros/RAs são
  snapshot do datario e CAS/CRE/APs vêm do data.rio (fases 3d/3g).

Faz o join pela chave normalizada da camada e calcula a taxa de
regularidade. Regiões sem dados ficam com ``taxa_regularidade=None``
(renderizadas em cinza no frontend); agregados sem geometria correspondente
(ex.: "NÃO IDENTIFICADO" em bairro, "Sem Vínculo" em RA, 12ª CRE) são
reportados no meta.

Camadas suportadas: ``bairro``, ``ra``, ``cas``, ``cre``, ``ap``.
"""

import asyncio
import re
import unicodedata
from typing import Any

from src.pic.application.ports.geospatial_repository import IGeospatialRepository
from src.pic.infrastructure.repositories.geometrias_estaticas_repository import (
    fetch_geometria_estatica,
)
from src.utils.log import logger

_CAMADAS_SUPORTADAS = ("bairro", "ra", "cas", "cre", "ap")

# Prefixo de ordinal do consolidado em RA ("3ª Rio Comprido" → "Rio Comprido").
_ORDINAL_PREFIX_RE = re.compile(r"^\d+\s*ª\s*")

# Só dígitos (para joins por código das camadas estáticas).
_DIGITOS_RE = re.compile(r"\D")

# Grafias divergentes do consolidado → datario (mesmo padrão de "Portuaria").
# A chave/valor já estão normalizados.
_RA_NOME_ALIASES: dict[str, str] = {
    "santa tereza": "santa teresa",
}


def normalize_bairro_nome(nome: str | None) -> str:
    """Normaliza nome de região para join: sem acentos, lowercase, sem espaços extras."""
    if not nome:
        return ""
    decomposed = unicodedata.normalize("NFKD", str(nome))
    ascii_only = "".join(c for c in decomposed if not unicodedata.combining(c))
    return ascii_only.strip().lower()


def normalize_ra_nome(nome: str | None) -> str:
    """Normaliza nome de RA removendo o ordinal ("3ª ") e aplicando aliases de grafia."""
    normalized = normalize_bairro_nome(_ORDINAL_PREFIX_RE.sub("", nome or ""))
    return _RA_NOME_ALIASES.get(normalized, normalized)


def normalize_codigo(codigo: str | None) -> str:
    """Chave de join por código: só dígitos, sem zeros à esquerda.

    Absorve as diferenças de formato entre consolidado e camadas do data.rio:
    ``"01ª CAS"`` → ``"1"`` (vs ``cas_label`` ``"1ª CAS"`` → ``"1"``),
    ``"AP 3.1"`` → ``"31"`` (vs ``id_ap`` ``"31"``), ``"01"`` → ``"1"``.
    ``"0"``/``"SEM VÍNCULO"`` → ``""`` (nunca casa → fica no meta).
    """
    return _DIGITOS_RE.sub("", str(codigo or "")).lstrip("0")


_NORMALIZERS: dict[str, Any] = {
    "bairro": normalize_bairro_nome,
    "ra": normalize_ra_nome,
    "cas": normalize_codigo,
    "cre": normalize_codigo,
    "ap": normalize_codigo,
}

# Fonte de geometria e campos por camada. `nome_field` é o campo usado na
# chave de join E no tooltip (nome exibido); `id_field` alimenta
# `properties.id` do GeoJSON.
_GEOMETRIA_SOURCES: dict[str, dict[str, str]] = {
    "bairro": {"id_field": "id_bairro", "nome_field": "nome"},
    "ra": {"id_field": "id_regiao_administrativa", "nome_field": "nome"},
    "cas": {"id_field": "cas", "nome_field": "cas_label"},
    "cre": {"id_field": "codigo", "nome_field": "nome"},
    "ap": {"id_field": "COD_AP_SMS", "nome_field": "COD_AP_SMS"},
}


async def _fetch_geometria(camada: str) -> list[dict[str, Any]]:
    """Geometria da camada — todas vêm dos GeoJSONs estáticos commitados (fase 3g)."""
    return fetch_geometria_estatica(camada)


class RegularidadePorCamadaOutput:
    def __init__(self, features: list[dict[str, Any]], meta: dict[str, Any]):
        self.features = features
        self.meta = meta


class GetRegularidadePorCamadaUseCase:
    def __init__(self, repository: IGeospatialRepository):
        self._repository = repository

    async def execute(
        self,
        camada: str,
        user_token: str | None = None,
        user_id: str | None = None,
        bypass_cache: bool = False,
        status: list[str] | None = None,
        cohortes: list[str] | None = None,
        protocolo_id: str | None = None,
    ) -> RegularidadePorCamadaOutput:
        if camada not in _CAMADAS_SUPORTADAS:
            raise ValueError(
                f"Camada {camada!r} não suportada (esperado: {_CAMADAS_SUPORTADAS})"
            )

        normalize = _NORMALIZERS[camada]
        id_field = _GEOMETRIA_SOURCES[camada]["id_field"]
        nome_field = _GEOMETRIA_SOURCES[camada]["nome_field"]

        aggregates, geometrias = await asyncio.gather(
            self._repository.fetch_regularidade_por_camada(
                camada=camada,
                user_token=user_token,
                user_id=user_id,
                bypass_cache=bypass_cache,
                status=status,
                cohortes=cohortes,
                protocolo_id=protocolo_id,
            ),
            _fetch_geometria(camada),
        )

        agg_by_nome = {normalize(agg.regiao): agg for agg in aggregates}

        features: list[dict[str, Any]] = []
        regioes_com_dados = 0
        regioes_sem_dados = 0

        for feature in geometrias:
            props = feature["properties"]
            agg = agg_by_nome.get(normalize(props[nome_field]))
            total = agg.total_participantes if agg else 0
            regulares = agg.total_regulares if agg else 0
            irregulares = agg.total_irregulares if agg else 0
            taxa = round(regulares / total * 100, 1) if total > 0 else None

            if taxa is None:
                regioes_sem_dados += 1
            else:
                regioes_com_dados += 1

            raw_id = props.get(id_field)
            properties: dict[str, Any] = {
                "id": str(raw_id) if raw_id is not None else None,
                "nome": props[nome_field],
                "total_participantes": total,
                "total_regulares": regulares,
                "total_irregulares": irregulares,
                "taxa_regularidade": taxa,
            }
            if camada == "bairro":
                properties["nome_regiao_administrativa"] = props.get(
                    "nome_regiao_administrativa"
                )

            features.append(
                {
                    "type": "Feature",
                    "properties": properties,
                    "geometry": feature["geometry"],
                }
            )

        # Agregados sem geometria correspondente na camada
        nomes_geometria = {
            normalize(f["properties"][nome_field]) for f in geometrias
        }
        agregados_sem_geometria = sorted(
            agg.regiao
            for agg in aggregates
            if normalize(agg.regiao) not in nomes_geometria
        )

        meta = {
            "camada": camada,
            "total_regioes": len(geometrias),
            "regioes_com_dados": regioes_com_dados,
            "regioes_sem_dados": regioes_sem_dados,
            "agregados_sem_geometria": agregados_sem_geometria,
        }
        logger.info(
            f"[geospatial] regularidade camada={camada!r} merged: "
            f"{regioes_com_dados} com dados, {regioes_sem_dados} sem dados, "
            f"{len(agregados_sem_geometria)} agregados sem geometria"
        )
        return RegularidadePorCamadaOutput(features=features, meta=meta)
