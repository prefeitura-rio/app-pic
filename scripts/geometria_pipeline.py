"""Pipeline compartilhado de simplificação/validação de geometrias estáticas.

Usado pelos scripts ``download_geometrias_data_rio.py`` (CAS/CRE/APs) e
``download_geometrias_datario.py`` (bairros/RAs) para aplicar o MESMO
tratamento em todas as camadas: simplificação com preservação de topologia
(shapely, tolerância ~11 m), reparo (``make_valid``) e validação (geometria
válida, anéis fechados, coordenadas finitas) antes de gravar o GeoJSON
commitado em ``src/pic/infrastructure/static/geojson/``.

shapely NÃO é dependência do app — os scripts rodam ad-hoc com
``uv run --with shapely``.
"""

import json
import math
from typing import Any

from shapely.geometry import GeometryCollection, MultiPolygon, Polygon, mapping, shape
from shapely.validation import make_valid

# Tolerância da simplificação em graus (~11 m; invisível no zoom de município).
SIMPLIFY_TOLERANCE_DEG = 0.0001

# Casas decimais das coordenadas na saída (6 ≈ 11 cm — bem abaixo da tolerância).
COORD_DECIMALS = 6


def polygonal(geom: object) -> Polygon | MultiPolygon | None:
    """Extrai a parte poligonal de uma geometria (make_valid pode gerar mistas)."""
    if isinstance(geom, (Polygon, MultiPolygon)):
        return geom
    if isinstance(geom, GeometryCollection):
        poligonos = []
        for parte in geom.geoms:
            if isinstance(parte, Polygon):
                poligonos.append(parte)
            elif isinstance(parte, MultiPolygon):
                poligonos.extend(parte.geoms)
        if not poligonos:
            return None
        return MultiPolygon(poligonos) if len(poligonos) > 1 else poligonos[0]
    return None


def round_coords(geom: Polygon | MultiPolygon) -> Polygon | MultiPolygon:
    def arredonda(anel: list[tuple[float, float]]) -> list[tuple[float, float]]:
        return [
            (round(lon, COORD_DECIMALS), round(lat, COORD_DECIMALS))
            for lon, lat in anel
        ]

    if isinstance(geom, Polygon):
        return Polygon(
            arredonda(list(geom.exterior.coords)),
            [arredonda(list(anel.coords)) for anel in geom.interiors],
        )
    return MultiPolygon(
        [
            Polygon(
                arredonda(list(poligono.exterior.coords)),
                [arredonda(list(anel.coords)) for anel in poligono.interiors],
            )
            for poligono in geom.geoms
        ]
    )


def simplify_geometry(geometry: dict) -> dict | None:
    """Simplifica preservando topologia, repara e devolve GeoJSON válido."""
    geom = shape(geometry)
    simplificada = geom.simplify(SIMPLIFY_TOLERANCE_DEG, preserve_topology=True)
    if not simplificada.is_valid:
        simplificada = make_valid(simplificada)
    poligonal = polygonal(simplificada)
    if poligonal is None or poligonal.is_empty:
        return None
    if not poligonal.is_valid:
        raise ValueError(f"geometria inválida após reparo: {poligonal.is_valid_reason}")
    return mapping(round_coords(poligonal))


def validate_features(features: list[dict], nome: str) -> None:
    """Garante geometria renderizável: válida, finita e com anéis fechados."""
    for index, feature in enumerate(features):
        geometry = feature["geometry"]
        geom = shape(geometry)
        if not geom.is_valid:
            raise ValueError(
                f"{nome}: geometria inválida na feature {index} "
                f"({geom.is_valid_reason})"
            )
        rings = (
            geometry["coordinates"]
            if geometry["type"] == "Polygon"
            else [ring for poly in geometry["coordinates"] for ring in poly]
        )
        for ring in rings:
            if ring and ring[0] != ring[-1]:
                raise ValueError(
                    f"{nome}: anel aberto na feature {index} ({geometry['type']})"
                )
            for lon, lat in ring:
                if not (math.isfinite(lon) and math.isfinite(lat)):
                    raise ValueError(
                        f"{nome}: coordenada não finita na feature {index}"
                    )


def count_pontos(features: list[dict]) -> int:
    total = 0
    for feature in features:
        geometry = feature["geometry"]
        rings = (
            geometry["coordinates"]
            if geometry["type"] == "Polygon"
            else [ring for poly in geometry["coordinates"] for ring in poly]
        )
        total += sum(len(ring) for ring in rings)
    return total


def escrever_feature_collection(
    features: list[dict], out_path: Any
) -> None:
    """Grava a FeatureCollection limpa (só ``type`` + ``features``), compacta."""
    clean: dict = {"type": "FeatureCollection", "features": features}
    out_path.write_text(
        json.dumps(clean, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
