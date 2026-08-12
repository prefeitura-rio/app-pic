from abc import ABC, abstractmethod
from typing import Any

import polars as pl

from src.pic.domain.models.filters import FilterCriteria, FilterVocabulary
from src.pic.domain.models.pagination import (
    PaginationMeta,
    PaginationParams,
    SortParams,
)
from src.pic.domain.models.participante import Participante, ParticipanteListItem


class IParticipantRepository(ABC):
    @abstractmethod
    async def find_paginated(
        self,
        filters: FilterCriteria,
        pagination: PaginationParams,
        sort: SortParams,
        permissions: Any = None,
        bypass_cache: bool = False,
    ) -> tuple[list[ParticipanteListItem], PaginationMeta]:
        ...

    @abstractmethod
    async def find_by_membro_familia(
        self,
        id_membro_familia: str,
        permissions: Any = None,
        bypass_cache: bool = False,
    ) -> Participante | None:
        ...

    @abstractmethod
    async def get_filter_vocabulary(
        self,
        filters: FilterCriteria,
        permissions: Any = None,
        bypass_cache: bool = False,
    ) -> FilterVocabulary:
        ...

    @abstractmethod
    async def export_dataframe(
        self,
        filters: FilterCriteria,
        sort: SortParams,
        permissions: Any = None,
        bypass_cache: bool = False,
    ) -> pl.DataFrame:
        ...
