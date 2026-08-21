"""
Configurações e constantes para o DataManager.
"""

from dataclasses import asdict, dataclass
from typing import Any


class DataManagerConfig:
    """
    Configurações centralizadas do DataManager.

    Todas as constantes usadas pelo DataManager devem estar aqui
    para facilitar ajustes e manutenção.
    """

    # Paginação
    DEFAULT_PAGE_SIZE = 20
    MIN_PAGE_SIZE = 1
    MAX_PAGE_SIZE = 10000

    # Profiling
    PROFILING_DECIMAL_PLACES = 3

    # Valores especiais de filtro (ignorados)
    FILTER_IGNORE_VALUES = {"todos", "todas", "", None}


class DataManagerError(Exception):
    """Exceção base para erros do DataManager."""

    pass


class ValidationError(DataManagerError):
    """Erro de validação de parâmetros."""

    pass


class FilterColumnNotFoundError(DataManagerError):
    """Erro quando coluna de filtro não existe no DataFrame."""

    def __init__(self, column: str, available_columns: list[str]):
        self.column = column
        self.available_columns = available_columns
        available_preview = ", ".join(available_columns[:10])
        if len(available_columns) > 10:
            available_preview += f"... ({len(available_columns)} total)"

        super().__init__(
            f"Filter column '{column}' not found in DataFrame. "
            f"Available columns: {available_preview}"
        )


class EmptyDatasetError(DataManagerError):
    """Erro quando dataset está vazio."""

    def __init__(self, query: str):
        self.query = query
        super().__init__(f"Query returned empty dataset: {query[:100]}...")


class PageOutOfRangeError(DataManagerError):
    """Erro quando página solicitada está fora do range."""

    def __init__(self, page: int, total_pages: int):
        self.page = page
        self.total_pages = total_pages
        super().__init__(f"Page {page} is out of range. Total pages: {total_pages}")


@dataclass
class ProfilingData:
    """
    Dados de profiling do pipeline de dados.

    Todos os tempos são em segundos (float).
    """

    get_dataset_s: float = 0.0
    cache_hit: bool = False
    apply_filters_s: float = 0.0
    search_s: float = 0.0
    filter_options_s: float = 0.0
    paginate_s: float = 0.0
    clean_s: float = 0.0
    convert_to_dict_s: float = 0.0  # Convert DataFrame to dict (JSON serialization)
    total_pipeline_s: float = 0.0

    # Metadados adicionais
    filters_applied: int = 0
    rows_before_filter: int = 0
    rows_after_filter: int = 0
    rows_after_search: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Converte para dicionário para serialização JSON."""
        return asdict(self)

    def __str__(self) -> str:
        """Representação legível para logs."""
        return (
            f"ProfilingData(total={self.total_pipeline_s:.3f}s, "
            f"cache_hit={self.cache_hit}, "
            f"get={self.get_dataset_s:.3f}s, "
            f"filter={self.apply_filters_s:.3f}s, "
            f"search={self.search_s:.3f}s, "
            f"filter_opts={self.filter_options_s:.3f}s, "
            f"paginate={self.paginate_s:.3f}s, "
            f"clean={self.clean_s:.3f}s, "
            f"to_dict={self.convert_to_dict_s:.3f}s)"
        )
