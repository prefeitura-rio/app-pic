from google.cloud import bigquery
from google.oauth2 import service_account
from typing import List, Dict, Any
import base64
import json
import time
import src.config.env as env
from src.utils.log import logger
from math import ceil
from src.utils.cache_manager import query_cache


def get_bigquery_result(
    query: str, page: int = 1, page_size: int = 100
) -> Dict[str, Any]:
    """
    Executes a BigQuery query (or retrieves from persistent cache) and returns the results
    with pagination logic applied in Python memory.
    """

    # Start overall profiling
    start_overall = time.perf_counter()
    profiling_data = {}

    # 1. Try to get data from persistent cache
    start_cache_lookup = time.perf_counter()
    all_data = query_cache.get(query)
    end_cache_lookup = time.perf_counter()
    profiling_data["cache_lookup_time_s"] = end_cache_lookup - start_cache_lookup
    is_cache_hit = all_data is not None

    # 2. If Miss, fetch from BigQuery
    if not is_cache_hit:
        logger.debug("Cache MISS - Fetching full dataset from BigQuery")
        start_bq_fetch = time.perf_counter()
        bq_client = get_bigquery_client()

        # Execute raw query to get everything
        query_job = bq_client.query(query)
        result = query_job.result()
        result_df = result.to_dataframe()
        all_data = result_df.to_json(
            orient="records",
        )
        all_data = json.loads(all_data)
        end_bq_fetch = time.perf_counter()
        profiling_data["bigquery_fetch_time_s"] = end_bq_fetch - start_bq_fetch

        # 3. Store in persistent cache
        start_cache_save = time.perf_counter()
        query_cache.set(query, all_data, profiling_data=profiling_data)
        end_cache_save = time.perf_counter()
        profiling_data["cache_save_time_s"] = end_cache_save - start_cache_save
    else:
        logger.debug("Cache HIT - Serving data from persistent storage")

    # 4. Pagination Logic (In-Memory)
    start_pagination = time.perf_counter()
    total_rows = len(all_data)

    if page < 1:
        page = 1
    if page_size < 1:
        page_size = 100

    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size

    paginated_data = all_data[start_idx:end_idx]
    total_pages = ceil(total_rows / page_size) if total_rows > 0 else 0
    end_pagination = time.perf_counter()
    profiling_data["pagination_logic_time_s"] = end_pagination - start_pagination

    end_overall = time.perf_counter()
    profiling_data["overall_execution_time_s"] = end_overall - start_overall

    logger.debug(f"Profiling Data: {json.dumps(profiling_data, indent=2)}")

    response = {
        "data": paginated_data,
        "meta": {
            "page": page,
            "page_size": page_size,
            "total_rows": total_rows,
            "total_pages": total_pages,
            "cache_hit": is_cache_hit,
            "profiling": profiling_data,  # Add profiling data to response meta as well
        },
    }

    return response


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
