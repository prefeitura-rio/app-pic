"""Baixa as geometrias territoriais estáticas (bairros, RAs) do datario.

Uso (shapely fora das dependências do app — execução pontual):
    uv run --with shapely python scripts/download_geometrias_datario.py

Contexto (plano de mapas — fase 3g): bairros e Regiões Administrativas
existem no datalake BQ (``datario.dados_mestres``), mas a aba Mapas passou a
servi-los como ARQUIVOS ESTÁTICOS (snapshot commitado) em vez de consultar o
BigQuery em runtime — isso remove o basedosdados/BQ do caminho do mapa,
elimina a latência de cold-start e reduz o payload servido (bairros:
~3,7 MB → ~525 KB; RAs: ~2,5 MB → ~300 KB), com a mesma simplificação
topológica das camadas do data.rio (~11 m, ``preserve_topology=True``).

Trade-off: a atualização deixa de ser automática (era cache de 24h) e vira
manual — rodar este script + redeploy quando o IPP publicar nova versão dos
limites (padrão idêntico ao das camadas CAS/CRE/APs).

Autenticação: lê ``src/config/.env`` (dotenv) e usa
``GCP_SERVICE_ACCOUNT_CREDENTIALS`` (base64 do JSON da service account —
mesmo formato usado pelo basedosdados no backend). As geometrias do datario
são WGS84 e válidas (verificado: 0 inválidas nas 167 + 33 feições).

O pipeline de simplificação/validação é compartilhado com o script do
data.rio em ``scripts/geometria_pipeline.py``.

Campos preservados (chaves de join do use case — não alterar):
- bairros: ``id_bairro``, ``nome``, ``nome_regiao_administrativa``
- ras: ``id_regiao_administrativa``, ``nome``
"""

import base64
import json
import sys
from pathlib import Path

import geometria_pipeline as pipeline
from dotenv import load_dotenv

_REPO_ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = _REPO_ROOT / "src" / "pic" / "infrastructure" / "static" / "geojson"

# Camada → tabela datario + campos preservados nas properties.
LAYERS: dict[str, dict] = {
    "bairros": {
        "tabela": "bairro",
        "select": ["id_bairro", "nome", "nome_regiao_administrativa"],
    },
    "ras": {
        "tabela": "regiao_administrativa",
        "select": ["id_regiao_administrativa", "nome"],
    },
}


def _carregar_env() -> dict[str, str]:
    load_dotenv(dotenv_path=_REPO_ROOT / "src" / "config" / ".env", override=True)
    import os

    return {
        "sa_b64": os.environ.get("GCP_SERVICE_ACCOUNT_CREDENTIALS", ""),
        "projeto": os.environ.get("BQ_PROJECT_ID", "rj-pic-dev"),
    }


def _baixar_features(tabela: str, campos: list[str], projeto: str, sa_b64: str) -> list[dict]:
    from google.cloud import bigquery
    from google.oauth2 import service_account

    info = json.loads(base64.b64decode(sa_b64))
    creds = service_account.Credentials.from_service_account_info(
        info, scopes=["https://www.googleapis.com/auth/bigquery"]
    )
    client = bigquery.Client(credentials=creds, project=projeto)

    colunas = ", ".join(campos)
    rows = [
        dict(r)
        for r in client.query(
            f"SELECT {colunas}, ST_AsGeoJSON(geometry) AS geometry_geojson "
            f"FROM `datario.dados_mestres.{tabela}`"
        ).result()
    ]

    features = []
    for row in rows:
        features.append(
            {
                "type": "Feature",
                "properties": {campo: row[campo] for campo in campos},
                "geometry": json.loads(row["geometry_geojson"]),
            }
        )
    return features


def main() -> None:
    env = _carregar_env()
    if not env["sa_b64"]:
        print(
            "ERRO: GCP_SERVICE_ACCOUNT_CREDENTIALS não encontrada em "
            "src/config/.env",
            file=sys.stderr,
        )
        sys.exit(1)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ok = True
    for nome, cfg in LAYERS.items():
        features_originais = _baixar_features(
            cfg["tabela"], cfg["select"], env["projeto"], env["sa_b64"]
        )
        pontos_originais = pipeline.count_pontos(features_originais)

        features: list[dict] = []
        for feature in features_originais:
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
                    "properties": feature["properties"],
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
