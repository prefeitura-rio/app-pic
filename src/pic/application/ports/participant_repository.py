"""Filter vocabulary + CSV export participant repository port.

The list/detail operations moved to `ParticipantRepository`
(`participant_read_repository.py`) on the PostgREST migration; these two
remain BigQuery/Polars-backed for now.
"""

from abc import ABC, abstractmethod
from typing import Any

import polars as pl

from src.pic.domain.models.filters import FilterCriteria, FilterVocabulary
from src.pic.domain.models.pagination import SortParams


class IParticipantRepository(ABC):
    @abstractmethod
    async def get_filter_vocabulary(
        self,
        filters: FilterCriteria,
        permissions: Any = None,
        bypass_cache: bool = False,
    ) -> FilterVocabulary: ...

    @abstractmethod
    async def export_dataframe(
        self,
        filters: FilterCriteria,
        sort: SortParams,
        permissions: Any = None,
        bypass_cache: bool = False,
    ) -> pl.DataFrame: ...
