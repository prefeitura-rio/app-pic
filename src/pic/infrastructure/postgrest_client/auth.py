"""Assinatura e renovação de JWT para autenticação no PostgREST."""

import time
from collections.abc import Callable

import jwt

JWT_ALGORITHM = "HS256"
JWT_EXPIRY_MARGIN_SECONDS = 60


class PostgrestJwtAuth:
    """Gera e cacheia tokens JWT HS256 assinados com o segredo do PostgREST."""

    def __init__(
        self,
        secret: str,
        *,
        role: str,
        ttl_seconds: int,
        expiry_margin_seconds: int = JWT_EXPIRY_MARGIN_SECONDS,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if not secret:
            raise ValueError("PostgREST JWT secret não pode ser vazio")
        if not role:
            raise ValueError("PostgREST role não pode ser vazio")
        if ttl_seconds <= expiry_margin_seconds:
            raise ValueError(
                "PostgREST JWT ttl_seconds deve ser maior que expiry_margin_seconds"
            )

        self._secret = secret
        self._role = role
        self._ttl_seconds = ttl_seconds
        self._expiry_margin_seconds = expiry_margin_seconds
        self._clock = clock
        self._token: str | None = None
        self._token_expires_at: float = 0.0

    def _generate_token(self) -> tuple[str, float]:
        now = int(self._clock())
        expires_at = now + self._ttl_seconds
        payload = {"role": self._role, "iat": now, "exp": expires_at}
        token = jwt.encode(payload, self._secret, algorithm=JWT_ALGORITHM)
        return token, float(expires_at)

    def _is_token_valid(self) -> bool:
        return self._token is not None and (
            self._clock() < self._token_expires_at - self._expiry_margin_seconds
        )

    def get_token(self) -> str:
        """Retorna o token atual, gerando um novo quando expirado ou ausente."""
        if not self._is_token_valid():
            self._token, self._token_expires_at = self._generate_token()
        return self._token

    def headers(self) -> dict[str, str]:
        """Retorna os headers de autorização com o token vigente."""
        return {"Authorization": f"Bearer {self.get_token()}"}

    def reset(self) -> None:
        """Descarta o token cacheado, forçando nova geração no próximo uso."""
        self._token = None
        self._token_expires_at = 0.0
