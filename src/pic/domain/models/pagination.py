from typing import Any

from pydantic import BaseModel, Field

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 10000


class PaginationParams(BaseModel):
    page: int = Field(1, ge=1)
    page_size: int = Field(
        DEFAULT_PAGE_SIZE,
        ge=-1,
        le=MAX_PAGE_SIZE,
    )


class SortParams(BaseModel):
    sort_by: str | None = None
    sort_order: str | None = Field("asc", pattern="^(asc|desc)$")


class PaginationMeta(BaseModel):
    page: int
    page_size: int | None = None
    total_rows: int
    total_pages: int
    cache_hit: bool
    profiling: Any | None = None
    can_view_dashboard: bool | None = None
