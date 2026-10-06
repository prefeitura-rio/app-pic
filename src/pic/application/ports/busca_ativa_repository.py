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
    async def get_members_with_busca_ativa(
        self,
        id_membros_familia: list[str],
        *,
        user_token: str | None = None,
        permissions: Any = None,
    ) -> set[str] | None:
        """Return which of the given members have at least one event.

        One aggregate query over `endpoint_busca_ativa` (group by
        `id_membro_familia`), respecting the same secretaria recorte as
        `get_busca_ativa`. Returns `None` on data-proxy failure (graceful
        degradation) — the caller leaves the list field unset.
        """
