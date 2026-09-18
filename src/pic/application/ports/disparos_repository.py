"""Read-side disparos repository port (WhatsApp disparos per participant).

Implemented by
`src.pic.infrastructure.repositories.disparos_repository`.  Reads are
best-effort: a data-proxy failure degrades to `None` (the participant detail
still succeeds) instead of raising.
"""

from abc import ABC, abstractmethod

from src.pic.domain.models.disparo import Disparo


class DisparosRepository(ABC):
    """Read-only access to the WhatsApp disparos of one participant."""

    @abstractmethod
    async def get_disparos(
        self,
        id_membro_familia: str,
        user_token: str | None = None,
    ) -> list[Disparo] | None:
        """Return the participant's disparos (one per campaign), newest first.

        `user_token` is the authenticated end user's JWT, forwarded so
        PostgREST applies row-level security. Returns `None` when the
        data-proxy read fails (graceful degradation) or `[]` when the
        participant has no disparos.
        """
