"""Unit tests for the static geometries repository (todas as 5 camadas).

Lê os GeoJSONs commitados em ``src/pic/infrastructure/static/geojson/``
(gerados por ``scripts/download_geometrias_data_rio.py`` e
``scripts/download_geometrias_datario.py``) — os testes são determinísticos
porque os arquivos fazem parte do repo.
"""

from __future__ import annotations

import pytest

from src.pic.infrastructure.repositories.geometrias_estaticas_repository import (
    fetch_geometria_estatica,
)


def _primeira_coord(geometry: dict) -> tuple[float, float]:
    """Primeiro par lon/lat da geometria (Polygon ou MultiPolygon)."""
    coords = geometry["coordinates"]
    if geometry["type"] == "MultiPolygon":
        return tuple(coords[0][0][0])
    return tuple(coords[0][0])


class TestFetchGeometriaEstatica:
    def test_bairros_retorna_167_features_wgs84(self):
        features = fetch_geometria_estatica("bairro")
        assert len(features) == 167
        props = features[0]["properties"]
        assert props.keys() >= {"id_bairro", "nome", "nome_regiao_administrativa"}
        assert features[0]["geometry"]["type"] in ("Polygon", "MultiPolygon")
        # Coordenadas em WGS84 (lon/lat do Rio) — nunca UTM
        lon, _ = _primeira_coord(features[0]["geometry"])
        assert -44.0 < lon < -43.0

    def test_ra_retorna_33_features(self):
        features = fetch_geometria_estatica("ra")
        assert len(features) == 33
        props = features[0]["properties"]
        assert props.keys() >= {"id_regiao_administrativa", "nome"}

    def test_cas_retorna_10_features_wgs84(self):
        features = fetch_geometria_estatica("cas")
        assert len(features) == 10
        props = features[0]["properties"]
        assert "cas" in props and "cas_label" in props
        assert features[0]["geometry"]["type"] in ("Polygon", "MultiPolygon")
        # Coordenadas em WGS84 (lon/lat do Rio) — nunca UTM
        lon, _ = _primeira_coord(features[0]["geometry"])
        assert -44.0 < lon < -43.0

    def test_cre_retorna_11_features(self):
        features = fetch_geometria_estatica("cre")
        assert len(features) == 11
        props = features[0]["properties"]
        assert "codigo" in props and "nome" in props

    def test_aps_retorna_10_features(self):
        # A camada da API é "ap"; internamente o arquivo é "aps.json"
        # (dataset "APs_da_Saúde" do data.rio).
        features = fetch_geometria_estatica("ap")
        assert len(features) == 10
        assert "COD_AP_SMS" in features[0]["properties"]

    def test_camada_desconhecida_levanta_value_error(self):
        with pytest.raises(ValueError, match="desconhecida"):
            fetch_geometria_estatica("municipio")

    def test_cache_reusa_mesma_lista(self):
        first = fetch_geometria_estatica("cre")
        second = fetch_geometria_estatica("cre")
        assert first is second

    def test_bypass_cache_rele_arquivo(self):
        first = fetch_geometria_estatica("ra")
        reloaded = fetch_geometria_estatica("ra", bypass_cache=True)
        assert first == reloaded  # mesmo conteúdo (arquivo idêntico)
        assert first is not reloaded  # mas relido do disco (nova lista)
