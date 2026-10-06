"""CSV streaming for the participant export (PostgREST wide rows).

The export pages come as plain dict rows (one per participant, wide-table
columns); this module turns them into the deterministic CSV defined by
`csv_columns` (fixed header + per-column transformations): UTF-8 BOM, `;`
delimiter, every value quoted, `""` for nulls, `_CHUNK_ROWS` lines buffered
per yielded chunk.
"""

import json
from collections.abc import AsyncIterator

from src.pic.infrastructure.export.config import _CHUNK_ROWS, _DELIMITER
from src.pic.infrastructure.export.csv_columns import transform_row


def _escape_csv(value: object) -> str:
    if value is None:
        return '""'
    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False)
    s = str(value).replace("\r", "").replace("\n", " ").replace('"', '""')
    return f'"{s}"'


def _row_line(row: dict[str, object], columns: list[str]) -> str:
    values = transform_row(row, columns)
    return _DELIMITER.join(_escape_csv(value) for value in values)


async def rows_to_csv_chunks(
    pages: AsyncIterator[list[dict[str, object]]],
    columns: list[str],
) -> AsyncIterator[bytes]:
    """Stream the export CSV as encoded chunks (BOM + header first)."""
    header_line = _DELIMITER.join(columns)
    yield ("\ufeff" + header_line + "\n").encode("utf-8")

    rows_buffer: list[str] = []
    async for page in pages:
        for row in page:
            rows_buffer.append(_row_line(row, columns))
            if len(rows_buffer) >= _CHUNK_ROWS:
                yield ("\n".join(rows_buffer) + "\n").encode("utf-8")
                rows_buffer = []

    if rows_buffer:
        yield ("\n".join(rows_buffer) + "\n").encode("utf-8")
