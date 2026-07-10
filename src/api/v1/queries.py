"""
Queries SQL centralizadas para os endpoints da API.

Este módulo centraliza todas as queries SQL usadas nos endpoints,
facilitando manutenção e garantindo consistência.
"""

from src.config import env

PROJECT_ID = env.BQ_PROJECT_ID
DATASET_ID = env.BQ_DATASET_ID
TABLE_ID_DATA_ACCESS = env.BQ_TABLE_ID_DATA_ACCESS
TABLE_ID_PARTICIPANTS = env.BQ_TABLE_ID_PARTICIPANTS_LISTAGEM
TABLE_ID_DASHBOARD = env.BQ_TABLE_ID_DASHBOARD
TABLE_ID_PARTICIPANTS_DEBUG = env.BQ_TABLE_ID_PARTICIPANTS_DEBUG
TABLE_ID_PARTICIPANTS_DEBUG_ORIGINS = env.BQ_TABLE_ID_PARTICIPANTS_DEBUG_ORIGINS
TABLE_ID_GEOSPATIAL_LAYERS = env.BQ_TABLE_ID_GEOSPATIAL_LAYERS

# ========================================================================
# GOVERNANCE QUERIES
# ========================================================================

GOVERNANCE_TABLE_QUERY = f"""
SELECT * FROM `{PROJECT_ID}.{DATASET_ID}.{TABLE_ID_DATA_ACCESS}`
ORDER BY cpf
"""


# ========================================================================
# PARTICIPANT QUERIES
# ========================================================================

PARTICIPANTS_TABLE_QUERY = f"""
SELECT *
FROM `{PROJECT_ID}.{DATASET_ID}.{TABLE_ID_PARTICIPANTS}`
ORDER BY nome ASC
"""


# ========================================================================
# DASHBOARD QUERIES
# ========================================================================

DASHBOARD_TABLE_QUERY = f"""
SELECT *
FROM `{PROJECT_ID}.{DATASET_ID}.{TABLE_ID_DASHBOARD}`
"""


# ========================================================================
# DEBUG QUERIES (Super Admin Only)
# ========================================================================

DEBUG_ORIGINS_QUERY = f"""
SELECT *
FROM `{PROJECT_ID}.{DATASET_ID}.{TABLE_ID_PARTICIPANTS_DEBUG_ORIGINS}`
"""


# ========================================================================
# GEOSPATIAL QUERIES
# ========================================================================

GEOSPATIAL_LAYERS_QUERY = f"""
SELECT
    * EXCEPT(geometry),
    ST_AsGeoJSON(geometry) as geometry_geojson
FROM `{PROJECT_ID}.{DATASET_ID}.{TABLE_ID_GEOSPATIAL_LAYERS}`
ORDER BY tipo_camada, categoria, nome
"""

# ========================================================================
# QUERY PARA MOTIVO DE IRREGULARIDADE
# ========================================================================
MOTIVO_IRREGULARIDADE_QUERY = f"""
SELECT *
FROM `{PROJECT_ID}.{DATASET_ID}.protocolo_detalhes`
WHERE protocolo_motivo IS NOT NULL
AND protocolo_id = "smas_acesso_cpf_certidao_nascimento"
AND PROTOCOLO_STATUS = "irregular"
"""