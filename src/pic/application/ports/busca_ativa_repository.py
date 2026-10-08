"""Read-side busca ativa repository port (busca ativa events per participant).

Implemented by
`src.pic.infrastructure.repositories.busca_ativa_repository`. Reads are
best-effort: a data-proxy failure degrades to `None` (the participant detail
still succeeds) instead of raising. Secretaria governance is applied by the
implementation using the caller's `permissions`.
"""

from abc import ABC, abstractmethod
from typing import Any

from src.pic.domain.models.busca_ativa import BuscaAtivaEvento


class BuscaAtivaRepository(ABC):
    """Read-only access to the busca ativa events of one participant."""

    @abstractmethod
    async def get_busca_ativa(
        self,
        id_membro_familia: str,
        *,
        user_token: str | None = None,
        offset: int = 0,
        limit: int = 20,
        permissions: Any = None,
    ) -> list[BuscaAtivaEvento] | None:
        """Return the participant's busca ativa events, newest first.

        `user_token` is the authenticated end user's JWT, forwarded so
        PostgREST applies row-level security. `permissions` drives the
        secretaria access recorte (fonte=SMS/SMAS). Returns `None` when the
        data-proxy read fails (graceful degradation), `[]` when the
        participant has no events (or the user has no secretaria access).
        """

    @abstractmethod
    async def get_busca_ativa_for_members(
        self,
        ids: list[str],
        *,
        user_token: str | None = None,
        permissions: Any = None,
        fontes: list[str] | None = None,
    ) -> list[tuple[str, BuscaAtivaEvento]]:
        """Return the busca ativa events of many participants at once.

        Bulk read for the CSV export: one `id_membro_familia=in.(...)` query
        per chunk (the ids are split app-side to keep the request URL within
        the proxy limits and issued concurrently), with the same
        `fonte=SMS/SMAS` secretaria recorte as `get_busca_ativa`. `fontes`
        further restricts the events to the selected `busca_ativa` filter
        (`None` means no filter recorte), intersected with the user's access.
        Each returned item is `(id_membro_familia, evento)` so the caller can
        group events back to their participant. Raises `PostgrestError` on a
        data-proxy failure (the export must not silently drop events); `[]`
        when the user has no SMS/SMAS access, the intersection is empty, or
        `ids` is empty.
        """
