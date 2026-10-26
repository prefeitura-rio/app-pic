"""Baixa as geometrias territoriais estáticas (CAS, CRE, APs) do data.rio.

Uso (shapely fora das dependências do app — execução pontual):
    uv run --with shapely python scripts/download_geometrias_data_rio.py

Contexto (plano de mapas — decisão A): essas camadas NÃO existem no datalake
BQ (``datario.*``) — a fonte é o ArcGIS Feature Server público do data.rio
(CC BY 4.0). Os arquivos são commitados em
``src/pic/infrastructure/static/geojson/`` e entram na imagem via o
``COPY src/`` já existente no Dockerfile (pipeline intocado). Rodar este
script manualmente quando a prefeitura publicar nova versão das camadas.

Por que simplificar LOCALMENTE (e não com ``maxAllowableOffset`` do ArcGIS):
- As camadas DECLARAM UTM (SIRGAS/SAD69 23S) nos metadados, mas servem
  coordenadas geográficas alinhadas ao datario (~5 m) — o ``outSR=4326`` é
  salvaguarda/idempotente para as APs (verificado ponto a ponto).
- O script baixa a geometria COMPLETA (oficial) e simplifica aqui com
  **shapely** (``preserve_topology=True``): Douglas-Peucker puro NÃO preserva
  topologia e deixou 6 das 10 APs inválidas (auto-interseção e "Hole lies
  outside shell") — o deck.gl/earcut então pintava áreas erradas (ex.: uma
  AP 4.0 "vazando" no oceano). O resultado é reparado com ``make_valid`` se
  necessário e validado antes de gravar.
- As fontes têm até ~19 mil vértices por polígono (~2,2 MB/camada) e anéis
  com pontos duplicados; após a simplificação (~11 m) cada camada fica
  ~135 KB, com anéis fechados e geometria válida.

O pipeline de simplificação/validação é compartilhado com o script do
datario em ``scripts/geometria_pipeline.py``.

A saída é limpa: FeatureCollection só com ``type`` + ``features``.

Atribuição (CC BY 4.0 — data.rio / Prefeitura do Rio):
- Limites CAS (SMAS) — item 2e43e6305ae8493c8fda8107998d214d
- Limites CRE (SME) — item fbfcbfae92654e248bdf1452cf260626
- APs da Saúde (SMS) — item b7b11fe05c984d4c9824c6081fcd57e2
"""

import json
import sys
import urllib.request
from pathlib import Path

import geometria_pipeline as pipeline

OUT_DIR = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "pic"
    / "infrastructure"
    / "static"
    / "geojson"
)

LAYERS: dict[str, dict] = {
    "cas": {
        "url": (
            "https://pgeo3.rio.rj.gov.br/arcgis/rest/services/Hosted/CAS_SMAS/"
            "FeatureServer/0/query?where=1%3D1&outFields=*&f=geojson&outSR=4326"
        ),
        "keep_props": ["cas", "cas_label"],
    },
    "cre": {
        "url": (
            "https://pgeo3.rio.rj.gov.br/arcgis/rest/services/Educacao/SME/"
            "MapServer/0/query?where=1%3D1&outFields=*&f=geojson&outSR=4326"
        ),
        "keep_props": ["codigo", "nome"],
    },
    "aps": {
        "url": (
            "https://services1.arcgis.com/OlP4dGNtIcnD3RYf/arcgis/rest/services/"
            "APs_da_Sa%C3%BAde/FeatureServer/0/query?where=1%3D1&outFields=*"
            "&f=geojson&outSR=4326"
        ),
        "keep_props": ["COD_AP_SMS"],
    },
}


def _download(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=120) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ok = True
    for nome, cfg in LAYERS.items():
        geojson = _download(cfg["url"])
        features: list[dict] = []
        pontos_originais = 0
        for feature in geojson.get("features", []):
            pontos_originais += pipeline.count_pontos([feature])
            try:
                geometry = pipeline.simplify_geometry(feature["geometry"])
            except ValueError as exc:
                print(f"ERRO em {nome}: {exc}", file=sys.stderr)
                ok = False
                break
            if geometry is None:
                continue
            features.append(
                {
                    "type": "Feature",
                    "properties": {
                        key: feature["properties"].get(key)
                        for key in cfg["keep_props"]
                    },
                    "geometry": geometry,
                }
            )
        else:
            try:
                pipeline.validate_features(features, nome)
            except ValueError as exc:
                print(f"ERRO: {exc}", file=sys.stderr)
                ok = False
                continue

            out_path = OUT_DIR / f"{nome}.json"
            pipeline.escrever_feature_collection(features, out_path)
            size_kb = out_path.stat().st_size / 1024
            print(
                f"{nome}: {len(features)} features, {pontos_originais} -> "
                f"{pipeline.count_pontos(features)} pontos, {size_kb:.1f} KB "
                f"-> {out_path}"
            )

    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
