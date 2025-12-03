from google.cloud import bigquery
from google.oauth2 import service_account
from typing import List, Optional
import base64
import json
import pandas as pd
import src.config.env as env
from src.utils.log import logger


def execute_query(query: str) -> pd.DataFrame:
    """
    Executes a BigQuery query and returns DataFrame directly.

    OTIMIZAÇÃO: Retorna DataFrame em vez de JSON.
    Isso evita conversões desnecessárias DataFrame → JSON → DataFrame.

    Returns:
        pd.DataFrame: Resultado da query do BigQuery
    """
    bq_client = get_bigquery_client()

    # Execute query e retornar DataFrame DIRETO
    query_job = bq_client.query(query)
    result = query_job.result()
    result_df = result.to_dataframe()

    logger.info(f"BigQuery returned {len(result_df)} rows as DataFrame")

    return result_df


def get_bigquery_client() -> bigquery.Client:
    credentials = get_gcp_credentials(
        scopes=[
            "https://www.googleapis.com/auth/drive",
            "https://www.googleapis.com/auth/cloud-platform",
        ]
    )
    return bigquery.Client(credentials=credentials, project=credentials.project_id)


def get_gcp_credentials(scopes: Optional[List[str]] = None) -> service_account.Credentials:
    info: dict = json.loads(base64.b64decode(env.GCP_SERVICE_ACCOUNT_CREDENTIALS))
    creds = service_account.Credentials.from_service_account_info(info)
    if scopes:
        creds = creds.with_scopes(scopes)
    return creds
