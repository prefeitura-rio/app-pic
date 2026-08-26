"""Configuration for the data-proxy PostgREST client.

All values come from `src.config.env` (see plan.md section 7). Nothing here
reads the environment directly - that keeps this module trivial to construct
with fake values in tests.
"""

from dataclasses import dataclass

from src.config import env


@dataclass(frozen=True)
class PostgrestClientConfig:
    """Everything needed to talk to one data-proxy schema as one Keycloak client."""

    base_url: str
    """data-proxy PostgREST base URL (e.g. https://data-proxy.staging.iplan.dados.rio/)."""

    schema: str
    """PostgREST schema to scope every request to (Accept-Profile/Content-Profile)."""

    token_url: str
    """Keycloak token endpoint for the client_credentials grant."""

    client_id: str
    """Keycloak client id. Its role claim determines the Postgres role PostgREST
    assumes (e.g. policy_writer_<schema>) - see data-proxy/docs/security.md."""

    client_secret: str


def load_config() -> PostgrestClientConfig:
    """Build the config from environment variables."""
    return PostgrestClientConfig(
        base_url=env.DATA_PROXY_API_URL,
        schema=env.DATA_PROXY_SCHEMA,
        token_url=env.DATA_PROXY_TOKEN_URL,
        client_id=env.DATA_PROXY_CLIENT_ID,
        client_secret=env.DATA_PROXY_CLIENT_SECRET,
    )
