"""Geometrias territoriais estáticas (bairro, RA, CAS, CRE, APs).

Todas as camadas da aba Mapas são servidas de GeoJSONs estáticos commitados
em ``src/pic/infrastructure/static/geojson/`` (embarcados na imagem pelo
``COPY src/`` do Dockerfile; pipeline intocado) — decisão A + fase 3g do
plano de mapas:

- ``bairro``/``ra``: snapshot do datario (IPP) gerado por
  ``scripts/download_geometrias_datario.py`` (antes eram consultas
  basedosdados/BQ em runtime com cache de 24h);
- ``cas``/``cre``/``ap``: camadas do data.rio (SMAS/SME/SMS — CC BY 4.0)
  geradas por ``scripts/download_geometrias_data_rio.py``.

Atualização: rodar o script correspondente quando a fonte publicar nova
versão (manual + redeploy; troca aceita para remover o BigQuery do caminho
do mapa e reduzir o payload servido em ~7x).

Campos por camada (após limpeza dos scripts):
- ``bairro``: ``id_bairro``, ``nome``, ``nome_regiao_administrativa``
- ``ra``: ``id_regiao_administrativa``, ``nome``
- ``cas``: ``cas`` (int), ``cas_label`` ("1ª CAS")
- ``cre``: ``codigo`` ("01"), ``nome`` ("1ª CRE")
- ``ap``: ``COD_AP_SMS`` ("AP 1.0")
"""

import json
from pathlib import Path
from typing import Any

_GEOMETRIAS_DIR = Path(__file__).resolve().parent.parent / "static" / "geojson"

_CAMADAS_ESTATICAS = ("bairro", "ra", "cas", "cre", "ap")

# Nome da camada → arquivo commitado (a camada "ap" vem do dataset "APs_da_Saúde").
_CAMADA_ARQUIVO: dict[str, str] = {
    "bairro": "bairros.json",
    "ra": "ras.json",
    "cas": "cas.json",
    "cre": "cre.json",
    "ap": "aps.json",
}

_cache: dict[str, list[dict[str, Any]]] = {}


def fetch_geometria_estatica(
    camada: str, bypass_cache: bool = False
) -> list[dict[str, Any]]:
    """Retorna as features GeoJSON (WGS84) da camada estática, com cache em memória.

    As camadas são pequenas (10–167 polígonos) e imutáveis entre deploys —
    o cache em memória é permanente (limpo apenas com novo processo).
    ``bypass_cache=True`` relê o arquivo do disco (paridade com o botão
    Atualizar das demais fontes).
    """
    if camada not in _CAMADAS_ESTATICAS:
        raise ValueError(f"Camada estática desconhecida: {camada!r}")

    if bypass_cache or camada not in _cache:
        path = _GEOMETRIAS_DIR / _CAMADA_ARQUIVO[camada]
        with open(path, encoding="utf-8") as fh:
            _cache[camada] = json.load(fh)["features"]

    return _cache[camada]
