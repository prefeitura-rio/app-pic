import pandas as pd
from typing import List, Dict, Any, TypeVar
from math import ceil
import json
import time

from src.utils.bigquery import execute_query
from src.utils.log import logger
from src.utils.cache_manager import query_cache
from src.api.v1.schemas import CommonFilters, PaginatedResponse, PaginationMeta

T = TypeVar('T')

class DataManager:
    """
    Centralized manager for fetching, caching, filtering, and paginating data.
    """

    @staticmethod
    def get_dataset(query: str) -> pd.DataFrame:
        """
        Retrieves the full dataset from cache or BigQuery and returns it as a Pandas DataFrame.
        """
        # 1. Try to get data from persistent cache
        raw_data = query_cache.get(query)
        
        if raw_data is not None:
            logger.debug("Cache HIT - Serving data from persistent storage")
        else:
            # 2. If Miss, fetch from BigQuery via Utility
            logger.debug("Cache MISS - Fetching full dataset from BigQuery")
            raw_data = execute_query(query)
            
            # 3. Store in persistent cache
            query_cache.set(query, raw_data)

        if not raw_data:
            return pd.DataFrame()
            
        return pd.DataFrame(raw_data)

    @staticmethod
    def apply_filters(df: pd.DataFrame, filters: CommonFilters) -> pd.DataFrame:
        """
        Applies filters to the DataFrame based on the provided CommonFilters.
        """
        if df.empty:
            return df

        # We operate on a copy or inplace? Pandas masking returns a new object usually.
        filtered_df = df

        if filters.bairro and filters.bairro != "todos":
            filtered_df = filtered_df[filtered_df['bairro'] == filters.bairro]
        
        if filters.cre and filters.cre != "todas":
            # Convert to string to ensure matching
            filtered_df = filtered_df[filtered_df['id_cre'].astype(str) == filters.cre]
            
        if filters.cras and filters.cras != "todas":
            filtered_df = filtered_df[filtered_df['id_cras'].astype(str) == filters.cras]
            
        if filters.safra and filters.safra != "todas":
            filtered_df = filtered_df[filtered_df['cohort'].astype(str) == filters.safra]
            
        if filters.grupo and filters.grupo != "todos":
            # Case insensitive substring search
            filtered_df = filtered_df[filtered_df['grupo'].astype(str).str.contains(filters.grupo, case=False, na=False)]
            
        if filters.status and filters.status != "todos":
            filtered_df = filtered_df[filtered_df['status'] == filters.status]

        return filtered_df

    @staticmethod
    def paginate_data(df: pd.DataFrame, page: int, page_size: int) -> PaginatedResponse[Any]:
        """
        Paginates the DataFrame and returns the full PaginatedResponse object.
        """
        start_time = time.perf_counter()
        
        total_rows = len(df)
        total_pages = ceil(total_rows / page_size) if total_rows > 0 else 0

        if page < 1:
            page = 1
        
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size

        # Slicing
        # Ensure column names are strings for dictionary keys before conversion
        df.columns = df.columns.astype(str)

        # Convert to dict records for JSON response
        paginated_data_raw = df.iloc[start_idx:end_idx].to_dict('records')
        
        # Explicitly convert each dictionary's keys to strings to satisfy type hint
        paginated_data: List[Dict[str, Any]] = []
        for item_dict in paginated_data_raw:
            strict_str_dict: Dict[str, Any] = {str(k): v for k, v in item_dict.items()}
            paginated_data.append(strict_str_dict)

        end_time = time.perf_counter()
        
        profiling = {
            "pagination_time_ms": (end_time - start_time) * 1000
        }

        return PaginatedResponse(
            data=paginated_data,
            meta=PaginationMeta(
                page=page,
                page_size=page_size,
                total_rows=total_rows,
                total_pages=total_pages,
                cache_hit=True, # In this architecture we always serve from memory/cache
                profiling=profiling
            )
        )

