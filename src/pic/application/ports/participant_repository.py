"""CSV export participant repository port.

The list/detail/vocabulary operations moved to `ParticipantRepository`
(`participant_read_repository.py`) on the PostgREST migration; only the CSV
export remains BigQuery/Polars-backed for now.
"""

from abc import ABC, abstractmethod
from typing import Any

import polars as pl

from src.pic.domain.models.filters import FilterCriteria
from src.pic.domain.models.pagination import SortParams


class IParticipantRepository(ABC):
    @abstractmethod
    async def export_dataframe(
        self,
        filters: FilterCriteria,
        sort: SortParams,
        permissions: Any = None,
        bypass_cache: bool = False,
    ) -> pl.DataFrame: ...
