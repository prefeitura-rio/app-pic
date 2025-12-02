from google.cloud import bigquery
from google.oauth2 import service_account
from typing import List, Dict, Any
import base64
import json
import decimal
import src.config.env as env
import datetime
import pytz
from src.utils.log import logger
from google.cloud.exceptions import GoogleCloudError
from src.config import env
from google.cloud.bigquery.table import Row
import numpy as np
import pandas as pd


class CustomJSONEncoder(json.JSONEncoder):
    """
    JSON Encoder customizado que sabe como converter objetos
    de data, hora e data/hora do Python para strings no padrão ISO 8601.
    """

    def default(self, obj):
        # Se o objeto for uma instância de datetime, date ou time...
        if isinstance(obj, (datetime.datetime, datetime.date, datetime.time)):
            # ... converta-o para uma string no formato ISO.
            return obj.isoformat()

        if isinstance(obj, decimal.Decimal):
            return float(obj)

        # Para qualquer outro tipo, deixe o encoder padrão fazer o trabalho.
        return super().default(obj)


def get_bigquery_result(query: str):
    bq_client = get_bigquery_client()
    query_job = bq_client.query(query)
    result = query_job.result(page_size=env.GOOGLE_BIGQUERY_PAGE_SIZE)
    data = []
    for page in result.pages:
        for row in page:
            row: Row
            row_data = dict(row.items())
            data.append(row_data)
    data_str = json.dumps(data, cls=CustomJSONEncoder, indent=2, ensure_ascii=False)

    return json.loads(data_str)


def get_bigquery_client() -> bigquery.Client:
    """Get the BigQuery client.

    Returns:
        bigquery.Client: The BigQuery client.
    """
    credentials = get_gcp_credentials(
        scopes=[
            "https://www.googleapis.com/auth/drive",
            "https://www.googleapis.com/auth/cloud-platform",
        ]
    )
    return bigquery.Client(credentials=credentials, project=credentials.project_id)


def get_gcp_credentials(scopes: List[str] = None) -> service_account.Credentials:
    """Get the GCP credentials.

    Args:
        scopes (List[str], optional): The scopes to use. Defaults to None.

    Returns:
        service_account.Credentials: The GCP credentials.
    """
    info: dict = json.loads(base64.b64decode(env.GCP_SERVICE_ACCOUNT_CREDENTIALS))
    creds = service_account.Credentials.from_service_account_info(info)
    if scopes:
        creds = creds.with_scopes(scopes)
    return creds


def get_datetime() -> str:
    timestamp = datetime.datetime.now(pytz.timezone("America/Sao_Paulo"))
    return timestamp.strftime("%Y-%m-%dT%H:%M:%S.%f")


def save_response_in_bq(
    data: dict,
    endpoint: str,
    dataset_id: str,
    table_id: str,
    project_id: str = "rj-iplanrio",
):
    table_full_name = f"{project_id}.{dataset_id}.{table_id}"
    logger.info(f"Salvando resposta no BigQuery: {table_full_name}")
    schema = [
        bigquery.SchemaField("datetime", "DATETIME", mode="NULLABLE"),
        bigquery.SchemaField("endpoint", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("data", "JSON", mode="NULLABLE"),
        bigquery.SchemaField("data_particao", "DATE", mode="NULLABLE"),
    ]

    job_config = bigquery.LoadJobConfig(
        schema=schema,
        # Optionally, set the write disposition. BigQuery appends loaded rows
        # to an existing table by default, but with WRITE_TRUNCATE write
        # disposition it replaces the table with the loaded data.
        write_disposition="WRITE_APPEND",
        time_partitioning=bigquery.TimePartitioning(
            type_=bigquery.TimePartitioningType.DAY,
            field="data_particao",  # name of column to use for partitioning
        ),
    )
    datetime_to_save = get_datetime()
    data_to_save = {
        "datetime": datetime_to_save,
        "endpoint": endpoint,
        "data": data,
        "data_particao": datetime_to_save.split("T")[0],
    }
    json_data = json.loads(json.dumps([data_to_save]))
    client = get_bigquery_client()

    try:
        job = client.load_table_from_json(
            json_data, table_full_name, job_config=job_config
        )
        job.result()
        logger.info(f"Resposta salva no BigQuery: {table_full_name}")
    except Exception:
        raise Exception(json_data)


def clean_json_field(obj):
    """
    Limpa campos JSON recursivamente: converte NaN para None,
    converte numpy/pandas types e força serialização válida.
    """
    if isinstance(obj, float) and np.isnan(obj):
        return None
    elif isinstance(obj, (np.generic, pd.Timestamp)):
        return obj.item() if hasattr(obj, "item") else str(obj)
    elif isinstance(obj, dict):
        return {k: clean_json_field(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [clean_json_field(v) for v in obj]
    else:
        return obj
