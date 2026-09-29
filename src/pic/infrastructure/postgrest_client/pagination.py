"""Generic PostgREST pagination over the PGRST_DB_MAX_ROWS cap.

The data-proxy caps every response at 1000 rows, so "fetch everything" loops
in pages of that size. These helpers own no domain knowledge — callers pass a
fresh query builder factory and receive raw rows — and wrap transport errors
into `PostgrestError`, same as the repositories did before this module.
"""

import asyncio
from collections.abc import Callable
from typing import Any

import httpx
from postgrest import APIResponse, AsyncSelectRequestBuilder
from postgrest.exceptions import APIError

from src.pic.infrastructure.postgrest_client.client import PostgrestClient
from src.pic.infrastructure.postgrest_client.errors import PostgrestError

# PGRST_DB_MAX_ROWS of the data-proxy: every response is capped at this many
# rows, so page fetches default to it.
DEFAULT_PAGE_SIZE = 1000

# How many pages are fetched concurrently (`asyncio.gather`) per window,
# re-emitted in offset order.
DEFAULT_PREFETCH_WINDOW = 3


async def execute_query(
    client: PostgrestClient, query: AsyncSelectRequestBuilder
) -> APIResponse:
    """Execute one query, mapping PostgREST/transport errors to PostgrestError."""
    try:
        return await query.execute()
    except APIError as error:
        raise PostgrestError.from_api_error(error) from error
    except httpx.HTTPError as error:
        raise PostgrestError.from_transport_error(error) from error


async def fetch_pages(
    client: PostgrestClient,
    build_query: Callable[..., AsyncSelectRequestBuilder],
    *,
    limit: int | None,
    with_count: bool,
    start_offset: int = 0,
    count_method: str = "estimated",
    batch_size: int = DEFAULT_PAGE_SIZE,
) -> tuple[list[dict[str, Any]], int | None]:
    """Fetch rows page by page, honoring PGRST_DB_MAX_ROWS.

    `limit=None` fetches everything (looping); otherwise stops once `limit`
    rows were collected, starting at `start_offset`. When `with_count` is
    set, the first page carries `Prefer: count=<method>` and the returned
    total comes from the `Content-Range` header (count of the *filtered*
    set, before limit/offset). `count_method` picks the PostgREST count
    mode: `exact` for views (no relation statistics for the `estimated`
    planner fallback) and `estimated` for plain tables.

    Contract: `build_query` MUST return a fresh query builder on every call.
    The postgrest-py builders are mutable (offset/limit/filters accumulate
    on the same instance), so reusing a captured builder across pages
    appends duplicate query params to each request.
    """
    batch_size = min(batch_size, DEFAULT_PAGE_SIZE)
    offset = start_offset
    rows: list[dict[str, Any]] = []
    total: int | None = None

    while True:
        query = build_query(
            count=count_method if with_count and total is None else None
        )
        page_limit = (
            min(batch_size, limit - len(rows)) if limit and limit > 0 else batch_size
        )
        result = await execute_query(client, query.offset(offset).limit(page_limit))
        page = list(result.data)
        if with_count and total is None:
            total = result.count

        rows.extend(page)
        offset += len(page)

        if limit and limit > 0 and len(rows) >= limit:
            break
        if len(page) < page_limit:
            break

    return rows, total


async def fetch_next_window(
    client: PostgrestClient,
    build_query: Callable[[], AsyncSelectRequestBuilder],
    offset: int,
    *,
    page_size: int = DEFAULT_PAGE_SIZE,
    window: int = DEFAULT_PREFETCH_WINDOW,
) -> tuple[list[list[dict[str, Any]]], int, bool]:
    """Fetch the next window of pages (up to `window`, concurrently) and
    return `(pages, next_offset, done)`.

    Pages are fetched with `offset`/`limit` and re-emitted in offset order;
    the first short page (< `page_size` rows) ends the stream (`done=True`),
    so the shared order (sort column + id) is stable across windows. A plain
    coroutine (not a generator) so the caller can scope `with_user_token` to
    the fetch itself and keep the ContextVar set/reset inside a single task.
    """
    page_size = min(page_size, DEFAULT_PAGE_SIZE)
    offsets = range(offset, offset + window * page_size, page_size)
    results = await asyncio.gather(
        *(
            execute_query(client, build_query().offset(off).limit(page_size))
            for off in offsets
        )
    )
    first_short = next(
        (i for i, result in enumerate(results) if len(result.data) < page_size),
        None,
    )
    last_index = len(results) - 1 if first_short is None else first_short
    pages = [list(results[i].data) for i in range(last_index + 1)]
    next_offset = offset + (last_index + 1) * page_size
    return pages, next_offset, first_short is not None
