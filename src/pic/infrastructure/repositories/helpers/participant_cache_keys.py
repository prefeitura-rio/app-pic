"""Deterministic Redis cache keys for the participant repository.

Keys are SHA-256 digests of the JSON-serialized request shape, isolating each
user (cpf). Kept separate from the query builders so this module stays about
cache identity only.
"""

import hashlib
import json

from src.pic.domain.models.filters import FilterCriteria
from src.pic.domain.models.pagination import PaginationParams, SortParams
from src.pic.infrastructure.repositories.helpers.participant_columns import (
    CACHE_PREFIX,
    VOCAB_CACHE_PREFIX,
)


def make_cache_key(
    filters: FilterCriteria,
    pagination: PaginationParams,
    sort: SortParams,
    user_id: str | None,
) -> str:
    """Deterministic cache key isolating each user (cpf) and request shape."""
    payload = json.dumps(
        {
            "filters": filters.model_dump(exclude_none=True),
            "page": pagination.page,
            "page_size": pagination.page_size,
            "sort_by": sort.sort_by,
            "sort_order": sort.sort_order,
            "user_id": user_id,
        },
        sort_keys=True,
        default=str,
    )
    return CACHE_PREFIX + hashlib.sha256(payload.encode()).hexdigest()


def make_vocab_cache_key(
    field: str, filters: FilterCriteria, user_id: str | None
) -> str:
    """Deterministic cache key for one filter field's options (per user cpf)."""
    payload = json.dumps(
        {
            "field": field,
            "filters": filters.model_dump(exclude_none=True),
            "user_id": user_id,
        },
        sort_keys=True,
        default=str,
    )
    return VOCAB_CACHE_PREFIX + hashlib.sha256(payload.encode()).hexdigest()
