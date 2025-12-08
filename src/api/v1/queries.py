"""
Queries SQL centralizadas para os endpoints da API.

Este módulo centraliza todas as queries SQL usadas nos endpoints,
facilitando manutenção e garantindo consistência.
"""

from src.config import env

PROJECT_ID = env.BQ_PROJECT_ID
DATASET_ID = env.BQ_DATASET_ID


# ========================================================================
# GOVERNANCE QUERIES
# ========================================================================

GOVERNANCE_TABLE_QUERY = f"""
SELECT * FROM `{PROJECT_ID}.{DATASET_ID}.data_access`
ORDER BY cpf
"""


# ========================================================================
# PARTICIPANT QUERIES
# ========================================================================

PARTICIPANTS_TABLE_QUERY = f"""
SELECT *
FROM `{PROJECT_ID}.{DATASET_ID}.endpoint_participante`
ORDER BY nome ASC
"""
