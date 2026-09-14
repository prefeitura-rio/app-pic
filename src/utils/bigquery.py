from google.cloud import bigquery
from google.oauth2 import service_account
from typing import List, Optional
import base64
import json
import polars as pl
import src.config.env as env
from src.utils.log import logger


def execute_query(
    query: str,
    parameters: Optional[List[bigquery.ScalarQueryParameter]] = None,
    return_polars: bool = True,  # Parâmetro mantido por compatibilidade, mas sempre retorna Polars
) -> pl.DataFrame:
    """
    Executes a BigQuery query and returns Polars DataFrame directly.

    OTIMIZAÇÃO V2: Retorna Polars DataFrame via Arrow (muito mais rápido).
    BigQuery → Arrow → Polars evita overhead de serialização Pandas.

    SEGURANÇA: Suporta parametrized queries para prevenir SQL injection.

    Args:
        query: SQL query (use @param_name para parametros)
        parameters: Lista de ScalarQueryParameter para binding seguro
        return_polars: Ignorado (sempre retorna Polars)

    Returns:
        pl.DataFrame: Resultado da query do BigQuery como Polars DataFrame
    """
    _ = return_polars  # Ignorado - sempre Polars

    bq_client = get_bigquery_client()

    # Configure job com parametros se fornecidos
    job_config = None
    if parameters:
        job_config = bigquery.QueryJobConfig(query_parameters=parameters)

    # Execute query
    query_job = bq_client.query(query, job_config=job_config)
    result = query_job.result()

    # OTIMIZAÇÃO: BigQuery → Arrow → Polars (evita Pandas overhead)
    arrow_table = result.to_arrow()
    result_df = pl.from_arrow(arrow_table)
    logger.info(f"BigQuery returned {len(result_df)} rows as Polars DataFrame (via Arrow)")

    return result_df


def build_update_query(
    table: str,
    updates: dict,
    where_field: str,
    where_value: str
) -> tuple[str, List[bigquery.ScalarQueryParameter]]:
    """
    Constrói UPDATE query parametrizada de forma segura.

    Args:
        table: Nome completo da tabela (project.dataset.table)
        updates: Dict com {campo: valor} para UPDATE
        where_field: Campo da cláusula WHERE
        where_value: Valor para WHERE clause

    Returns:
        (query_string, parameters_list)

    Example:
        query, params = build_update_query(
            "project.dataset.users",
            {"nome": "João", "active": True},
            "cpf",
            "12345678900"
        )
        # query = "UPDATE `project.dataset.users` SET nome = @nome, active = @active WHERE cpf = @cpf"
        # params = [ScalarQueryParameter("nome", "STRING", "João"), ...]
    """
    # Build SET clause
    set_clauses = []
    parameters = []

    for field, value in updates.items():
        set_clauses.append(f"{field} = @{field}")

        # Determinar tipo BigQuery
        if value is None:
            param_type = "STRING"
        elif isinstance(value, bool):
            param_type = "BOOL"
        elif isinstance(value, int):
            param_type = "INT64"
        elif isinstance(value, float):
            param_type = "FLOAT64"
        else:
            param_type = "STRING"
            value = str(value)

        parameters.append(bigquery.ScalarQueryParameter(field, param_type, value))

    # Add WHERE parameter
    parameters.append(bigquery.ScalarQueryParameter(where_field, "STRING", where_value))

    # Build query
    query = f"""
        UPDATE `{table}`
        SET {', '.join(set_clauses)}
        WHERE {where_field} = @{where_field}
    """

    return query, parameters


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
