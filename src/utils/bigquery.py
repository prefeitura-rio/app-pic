from google.cloud import bigquery
from google.oauth2 import service_account
from typing import List, Dict, Any
import base64
import json
import src.config.env as env
from src.utils.log import logger


def execute_query(query: str) -> List[Dict[str, Any]]:
    """
    Executes a BigQuery query and returns the raw results as a list of dictionaries.
    No caching or pagination is performed here.
    """
    bq_client = get_bigquery_client()

    # Execute raw query to get everything
    query_job = bq_client.query(query)
    result = query_job.result()
    result_df = result.to_dataframe()
    
    # Serialize to JSON-compatible format (handling dates, etc.)
    all_data_json = result_df.to_json(
        orient="records",
        date_format="iso",
    )
    all_data = json.loads(all_data_json)
    
    return all_data


def get_bigquery_client() -> bigquery.Client:
    credentials = get_gcp_credentials(
        scopes=[
            "https://www.googleapis.com/auth/drive",
            "https://www.googleapis.com/auth/cloud-platform",
        ]
    )
    return bigquery.Client(credentials=credentials, project=credentials.project_id)


def get_gcp_credentials(scopes: List[str] = None) -> service_account.Credentials:
    info: dict = json.loads(base64.b64decode(env.GCP_SERVICE_ACCOUNT_CREDENTIALS))
    creds = service_account.Credentials.from_service_account_info(info)
    if scopes:
        creds = creds.with_scopes(scopes)
    return creds
