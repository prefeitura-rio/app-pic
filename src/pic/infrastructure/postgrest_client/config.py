"""Configuração do client PostgREST."""

from dataclasses import dataclass

from src.utils.infisical import getenv_or_action

DEFAULT_SCHEMA = "app_pequenos_cariocas"
DEFAULT_ROLE = "authenticator"
DEFAULT_JWT_TTL_SECONDS = 3600
DEFAULT_TIMEOUT_SECONDS = 30.0
DEFAULT_MAX_CONNECTIONS = 50


@dataclass(frozen=True, slots=True)
class PostgrestConfig:
    """Configuração lida do ambiente para o client PostgREST.

    O ``jwt_secret`` é opcional: quando ausente, o client funciona apenas
    com o token Keycloak do usuário (contextvar), sem fallback de serviço.
    """

    url: str
    jwt_secret: str | None
    schema: str = DEFAULT_SCHEMA
    role: str = DEFAULT_ROLE
    jwt_ttl_seconds: int = DEFAULT_JWT_TTL_SECONDS
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    max_connections: int = DEFAULT_MAX_CONNECTIONS


def load_postgrest_config() -> PostgrestConfig:
    """Carrega as variáveis de ambiente do PostgREST.

    Raises:
        EnvironmentError: Se POSTGREST_URL não estiver definida.
    """
    url = getenv_or_action("POSTGREST_URL", action="raise")
    jwt_secret = getenv_or_action("POSTGREST_JWT_SECRET", action="ignore")
    schema = getenv_or_action(
        "POSTGREST_SCHEMA", action="ignore", default=DEFAULT_SCHEMA
    )
    role = getenv_or_action("POSTGREST_ROLE", action="ignore", default=DEFAULT_ROLE)
    jwt_ttl_seconds = int(
        getenv_or_action(
            "POSTGREST_JWT_TTL_SECONDS",
            action="ignore",
            default=str(DEFAULT_JWT_TTL_SECONDS),
        )
    )
    timeout_seconds = float(
        getenv_or_action(
            "POSTGREST_TIMEOUT_SECONDS",
            action="ignore",
            default=str(DEFAULT_TIMEOUT_SECONDS),
        )
    )
    max_connections = int(
        getenv_or_action(
            "POSTGREST_MAX_CONNECTIONS",
            action="ignore",
            default=str(DEFAULT_MAX_CONNECTIONS),
        )
    )

    return PostgrestConfig(
        url=url,
        jwt_secret=jwt_secret,
        schema=schema,
        role=role,
        jwt_ttl_seconds=jwt_ttl_seconds,
        timeout_seconds=timeout_seconds,
        max_connections=max_connections,
    )
