import pandas as pd
import numpy as np
from typing import List, Dict, Any, TypeVar, Optional
from math import ceil
import time
import unicodedata

from src.utils.bigquery import execute_query
from src.utils.log import logger
from src.utils.cache_manager import query_cache
from src.api.v1.schemas import (
    PaginatedResponse,
    PaginationMeta,
    SmartFilterOptions,
    FilterOptionItem,
)

T = TypeVar("T")


def normalize_string(text: str) -> str:
    """
    Normaliza string removendo acentos e convertendo para lowercase.

    Exemplos:
        'Criança' -> 'crianca'
        'São Paulo' -> 'sao paulo'
        'GESTANTE' -> 'gestante'
    """
    # Normaliza para NFD (decompõe caracteres acentuados)
    nfd = unicodedata.normalize("NFD", text)
    # Remove marcas diacríticas (acentos)
    without_accents = "".join(
        char for char in nfd if unicodedata.category(char) != "Mn"
    )
    # Converte para lowercase
    return without_accents.lower()


class DataManager:
    """
    Centralized manager for fetching, caching, filtering, and paginating data.
    Genérico - não conhece as colunas específicas, recebe tudo via parâmetros.
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
    def apply_filters(df: pd.DataFrame, filters_dict: Dict[str, Any]) -> pd.DataFrame:
        """
        Aplica filtros ao DataFrame usando .isin() do pandas.

        Args:
            df: DataFrame a ser filtrado
            filters_dict: {nome_coluna: valor_ou_lista_de_valores}
                         Ex: {'bairro': '46', 'grupo': 'Gestante'}
                         Ex: {'bairro': ['46', '47'], 'status': ['ativo']}

        Returns:
            DataFrame filtrado
        """
        if df.empty:
            return df

        initial_rows = len(df)
        df_filtered = df.copy()

        # Aplicar cada filtro usando .isin()
        for col, filter_value in filters_dict.items():
            # Pular se coluna não existe
            if col not in df_filtered.columns:
                logger.warning(
                    f"Column '{col}' not found in DataFrame. Available columns: {list(df_filtered.columns)}"
                )
                continue

            # Converter para lista se não for
            if not isinstance(filter_value, list):
                filter_value = [filter_value]

            # Pular valores vazios
            filter_value = [
                v
                for v in filter_value
                if v and str(v).strip() and str(v) not in ("todos", "todas")
            ]
            if not filter_value:
                continue

            # Aplicar filtro usando .isin() - case-insensitive e sem acentos
            # Normalizar tanto os valores do DataFrame quanto os filtros
            normalized_filter_values = [normalize_string(str(v)) for v in filter_value]
            df_filtered = df_filtered[
                df_filtered[col]
                .astype(str)
                .apply(normalize_string)
                .isin(normalized_filter_values)
            ]

        # Log apenas se mudou algo
        if initial_rows != len(df_filtered):
            logger.info(f"Filters applied: {initial_rows} -> {len(df_filtered)} rows")

        return df_filtered

    @staticmethod
    def calculate_filter_options(
        df: pd.DataFrame, columns_config: Dict[str, Dict[str, str]]
    ) -> SmartFilterOptions:
        """
        Calcula opções de filtros disponíveis usando .unique() do pandas.

        Args:
            df: DataFrame com os dados
            columns_config: Configuração de colunas
                {
                    'bairros': {'column': 'bairro'},
                    'cras': {'column': 'id_cras', 'label_column': 'nome_cras'},
                }

        Returns:
            SmartFilterOptions com valores únicos por coluna
        """
        if df.empty:
            return SmartFilterOptions()

        filter_options_dict = {}

        for result_key, config in columns_config.items():
            column = config.get("column")
            label_column = config.get("label_column")

            # Pular se coluna não existe
            if not column or column not in df.columns:
                filter_options_dict[result_key] = []
                continue

            # Pegar valores únicos
            unique_values = df[column].dropna().unique()

            # Criar dict de labels se tiver coluna de label
            label_map = {}
            if label_column and label_column in df.columns:
                label_map = (
                    df[[column, label_column]]
                    .dropna()
                    .drop_duplicates(column)
                    .set_index(column)[label_column]
                    .to_dict()
                )

            # Criar lista de opções
            options = []
            for value in unique_values:
                value_str = str(value).strip()
                if not value_str:
                    continue

                options.append(
                    FilterOptionItem(
                        id=value_str, label=str(label_map.get(value, value))
                    )
                )

            # Ordenar por label
            options.sort(key=lambda x: x.label)
            filter_options_dict[result_key] = options

        return SmartFilterOptions(**filter_options_dict)

    @staticmethod
    def paginate_data(
        df: pd.DataFrame,
        page: int,
        page_size: int,
        filter_columns_config: Optional[Dict[str, Dict[str, str]]] = None,
    ) -> PaginatedResponse[Any]:
        """
        Paginates the DataFrame and returns the full PaginatedResponse object.
        Optionally includes dynamic filter options based on the filtered data.

        Args:
            df: DataFrame to paginate
            page: Page number (1-indexed)
            page_size: Items per page
            filter_columns_config: Config for filter options (optional)
                {
                    'bairros': {'column': 'bairro'},
                    'cras': {'column': 'id_cras', 'label_column': 'nome_cras'},
                }
        """
        start_time = time.perf_counter()

        total_rows = len(df)
        total_pages = ceil(total_rows / page_size) if total_rows > 0 else 0

        if page < 1:
            page = 1

        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size

        # Handle NaN/Inf values which are not valid JSON
        df_clean = df.replace([np.inf, -np.inf, np.nan], None)

        # Ensure column names are strings for dictionary keys before conversion
        df_clean.columns = df_clean.columns.astype(str)

        paginated_data_raw = df_clean.iloc[start_idx:end_idx].to_dict("records")

        # Explicitly convert each dictionary's keys to strings to satisfy type hint
        paginated_data: List[Dict[str, Any]] = []
        for item_dict in paginated_data_raw:
            strict_str_dict: Dict[str, Any] = {str(k): v for k, v in item_dict.items()}
            paginated_data.append(strict_str_dict)

        # Calculate filter options based on the full filtered dataset (before pagination)
        filter_options_dict = None
        if filter_columns_config:
            filter_options_dict = DataManager.calculate_filter_options(
                df, filter_columns_config
            )

        end_time = time.perf_counter()

        profiling = {"pagination_time_ms": (end_time - start_time) * 1000}

        return PaginatedResponse(
            data=paginated_data,
            meta=PaginationMeta(
                page=page,
                page_size=page_size,
                total_rows=total_rows,
                total_pages=total_pages,
                cache_hit=True,
                profiling=profiling,
            ),
            filters=filter_options_dict,
        )
