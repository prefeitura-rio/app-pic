"""Errors raised by PostgREST requests."""

from postgrest.exceptions import APIError


class PostgrestError(Exception):
    """PostgREST request failed (HTTP error, schema mismatch, or network).

    Carries the structured fields the data-proxy returns on error
    (`message`, `code`, `details`, `hint`) when available, so callers can log
    and surface a useful detail to the client.
    """

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        details: str | None = None,
        hint: str | None = None,
    ) -> None:
        self.message = message
        self.code = code
        self.details = details
        self.hint = hint
        super().__init__(message)

    def __str__(self) -> str:
        return self.message

    @classmethod
    def from_api_error(cls, error: APIError) -> "PostgrestError":
        """Build from a `postgrest.exceptions.APIError`.

        When postgrest-py could not parse the upstream error body it produces
        the generic "JSON could not be generated" message; in that case the
        real upstream text is in `details` (e.g. PostgREST's plain-text JWT
        validation errors), so it is promoted to the message.
        """
        message = error.message
        details = error.details
        if not message or message == "JSON could not be generated":
            cleaned = cls._clean_details(details)
            message = cleaned or message or str(error)
        return cls(
            message,
            code=error.code,
            details=details,
            hint=error.hint,
        )

    @staticmethod
    def _clean_details(details: str | None) -> str | None:
        """Strip the `b'...'` bytes repr postgrest-py wraps raw bodies in."""
        if not details:
            return None
        cleaned = details.strip()
        if cleaned.startswith("b'") and cleaned.endswith("'"):
            cleaned = cleaned[2:-1]
        return cleaned or None

    @classmethod
    def from_transport_error(cls, error: Exception) -> "PostgrestError":
        """Build from an httpx transport error (connection refused, timeout...)."""
        return cls(f"Falha de comunicação com o data-proxy (PostgREST): {error}")
