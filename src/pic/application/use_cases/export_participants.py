from typing import Any

import polars as pl

from src.pic.application.ports.participant_repository import IParticipantRepository
from src.pic.domain.models.filters import FilterCriteria
from src.pic.domain.models.pagination import SortParams

SENSITIVE_COLUMNS = ["latitude", "longitude"]


class ExportOutput:
    def __init__(self, df: pl.DataFrame):
        self.df = df
        self.total_rows = len(df)


class ExportParticipantsUseCase:
    def __init__(self, repository: IParticipantRepository):
        self._repository = repository

    async def execute(
        self,
        filters: FilterCriteria,
        sort: SortParams,
        permissions: Any = None,
        bypass_cache: bool = False,
    ) -> ExportOutput:
        df = await self._repository.export_dataframe(
            filters=filters,
            sort=sort,
            permissions=permissions,
            bypass_cache=bypass_cache,
        )

        if permissions and not permissions.is_super_admin:
            cols_to_drop = [c for c in SENSITIVE_COLUMNS if c in df.columns]
            if cols_to_drop:
                df = df.drop(cols_to_drop)

        return ExportOutput(df=df)
