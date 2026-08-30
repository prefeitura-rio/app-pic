"""Shared helpers for the v2 routes (data-proxy token pick, error mapping)."""

from src.pic.application.ports.admin_repository import IAdminRepository
from src.pic.infrastructure.postgrest_client.errors import PostgrestError
from src.utils.log import logger


def data_proxy_user_token(data_proxy_token: str | None, id_token: str) -> str:
    """Pick the token forwarded to the data-proxy (PostgREST).

    Prefers the `X-Access-Token` header (Keycloak access token, which carries
    the `role`/`schemas` claims PostgREST needs); falls back to the id token
    used for backend auth when the header is absent (older sessions).
    """
    if data_proxy_token:
        token = data_proxy_token.strip()
        if token.lower().startswith("bearer "):
            token = token[7:].strip()
        if token:
            return token
    return id_token


def log_postgrest_error(error: PostgrestError) -> None:
    logger.error(
        f"PostgREST (data-proxy) error: message={error.message} "
        f"code={error.code} hint={error.hint} details={error.details}"
    )


async def self_heal_policy_sync(admin_repo: IAdminRepository, cpf: str) -> None:
    """Best-effort push of pending policy grants before the data-proxy read.

    The frontend loads `/admin/me` (which runs the same self-heal) and the
    data endpoints in parallel; on a first login with pending grants, the
    queries could otherwise hit the data-proxy before the sync and return
    empty results. Never blocks the read on failure.
    """
    try:
        await admin_repo.self_heal_policy_sync(cpf)
    except Exception:
        logger.exception(f"Self-heal de policy sync falhou para {cpf}")
