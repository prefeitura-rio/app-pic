from typing import Annotated, Any

import httpx
import jwt
from fastapi import Depends, HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.config import env
from src.utils.log import logger

security = HTTPBearer()

# Cache for JWKS keys
_jwks_cache: dict[str, Any] = {}


async def get_jwks() -> dict[str, Any]:
    """Fetch JWKS from RMI (Keycloak) and cache it."""
    if _jwks_cache:
        return _jwks_cache

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(env.RMI_JWKS_URL)
            response.raise_for_status()
            jwks = response.json()
            _jwks_cache.update(jwks)
            return jwks
    except Exception as e:
        logger.error(f"❌ Failed to fetch JWKS: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch JWKS") from e


def get_signing_key(token: str, jwks: dict[str, Any]) -> Any:
    """Get the signing key from JWKS for the given token."""
    try:
        unverified_header = jwt.get_unverified_header(token)
        rsa_key = {}

        for key in jwks.get("keys", []):
            if key["kid"] == unverified_header["kid"]:
                rsa_key = {
                    "kty": key["kty"],
                    "kid": key["kid"],
                    "use": key["use"],
                    "n": key["n"],
                    "e": key["e"],
                }
                break

        if not rsa_key:
            raise HTTPException(
                status_code=401, detail="Unable to find appropriate key"
            )

        return jwt.algorithms.RSAAlgorithm.from_jwk(rsa_key)
    except Exception as e:
        logger.error(f"❌ Error getting signing key: {e}")
        raise HTTPException(status_code=401, detail="Invalid token header") from e


async def verify_jwt(
    credentials: HTTPAuthorizationCredentials = Security(security),
) -> dict[str, Any]:
    """
    Verify JWT token from Authorization header.
    Returns the decoded token payload if valid.
    """
    token = credentials.credentials

    try:
        # Get JWKS
        jwks = await get_jwks()

        # Get signing key
        signing_key = get_signing_key(token, jwks)

        # Decode and verify token
        payload = jwt.decode(
            token,
            signing_key,
            algorithms=["RS256"],
            audience=env.RMI_AUDIENCE,
            issuer=env.RMI_ISSUER,
            leeway=60,  # Tolerância de 60 segundos para clock skew (iat/exp)
        )

        logger.info(f"Token verified for user: {payload.get('sub')}")
        return payload

    except jwt.ExpiredSignatureError as e:
        logger.warning("Token has expired")
        raise HTTPException(status_code=401, detail="Token has expired") from e
    except jwt.InvalidAudienceError as e:
        logger.warning("Invalid token audience")
        raise HTTPException(status_code=401, detail="Invalid token audience") from e
    except jwt.InvalidIssuerError as e:
        logger.warning("Invalid token issuer")
        raise HTTPException(status_code=401, detail="Invalid token issuer") from e
    except jwt.InvalidTokenError as e:
        logger.warning(f"Invalid token: {e}")
        raise HTTPException(status_code=401, detail="Invalid token") from e
    except Exception as e:
        logger.error(f"❌ Token verification failed: {e}")
        raise HTTPException(
            status_code=401, detail="Could not validate credentials"
        ) from e


async def get_current_user_permissions(
    token_payload: dict[str, Any] = Depends(verify_jwt),
):
    """
    Get current user's permissions from data_access table (BigQuery).

    Used by v1 (legacy) routes only. Extracts CPF from JWT token and loads
    permissions from the BigQuery governance table (endpoint_data_access).
    Uses the DataManager's shared cache for performance.

    v2 routes use `get_current_user_permissions_v2` instead (Postgres-backed).
    Do NOT swap this for the Postgres-backed version: v1's admin CRUD still
    writes to BigQuery, so v1 auth must keep reading from BigQuery too.

    Args:
        token_payload: Decoded JWT token from verify_jwt

    Returns:
        UserPermissions object

    Raises:
        HTTPException 403: If CPF not found in token or user not authorized
        HTTPException 500: If failed to load permissions
    """
    import time
    perm_start = time.perf_counter()

    from src.core.security.permissions_models import PermissionDeniedError
    from src.utils.data_manager import DataManager

    # Extract CPF from JWT (RMI/gov.br sends it in preferred_username)
    cpf = token_payload.get("preferred_username")

    if not cpf:
        logger.error("❌ CPF not found in JWT token")
        raise HTTPException(
            status_code=403, detail="CPF não encontrado no token de autenticação"
        )

    try:
        permissions = await DataManager.get_user_permissions(cpf)
        perm_time = time.perf_counter() - perm_start
        logger.info(
            f"⏱️ [TIMING] get_user_permissions took {perm_time:.3f}s - "
            f"User authenticated (Admin: {permissions.is_admin}, SuperAdmin: {permissions.is_super_admin})"
        )
        return permissions

    except PermissionDeniedError as e:
        error_msg = str(e)
        logger.warning(f"Permission denied for CPF {cpf}: {error_msg}")
        raise HTTPException(
            status_code=403,
            detail=error_msg,  # Passar a mensagem específica da PermissionDeniedError
        ) from e
    except Exception as e:
        logger.error(f"❌ Error loading permissions for CPF {cpf}: {e}")
        raise HTTPException(
            status_code=500, detail="Falha ao carregar permissões do usuário"
        ) from e


async def get_current_user_permissions_v2(
    token_payload: dict[str, Any] = Depends(verify_jwt),
):
    """
    Get current user's permissions from Postgres (users/policy tables).

    Used by v2 routes only. Extracts CPF from JWT token and loads permissions
    via PostgresAdminRepository. This is the hot path: it does NOT join
    against the participants catalog, so id_*_list entries have `nome == id`
    as a fallback (real names require fetch_governance_df).

    Args:
        token_payload: Decoded JWT token from verify_jwt

    Returns:
        UserPermissions object

    Raises:
        HTTPException 403: If CPF not found in token or user not authorized
        HTTPException 500: If failed to load permissions
    """
    import time
    perm_start = time.perf_counter()

    from src.core.security.permissions_models import PermissionDeniedError
    from src.pic.infrastructure.repositories.postgres_admin import (
        PostgresAdminRepository,
    )

    # Extract CPF from JWT (RMI/gov.br sends it in preferred_username)
    cpf = token_payload.get("preferred_username")

    if not cpf:
        logger.error("❌ CPF not found in JWT token")
        raise HTTPException(
            status_code=403, detail="CPF não encontrado no token de autenticação"
        )

    try:
        permissions = await PostgresAdminRepository().fetch_user_permissions(cpf)
        perm_time = time.perf_counter() - perm_start
        logger.info(
            f"⏱️ [TIMING] fetch_user_permissions took {perm_time:.3f}s - "
            f"User authenticated (Admin: {permissions.is_admin}, SuperAdmin: {permissions.is_super_admin})"
        )
        return permissions

    except PermissionDeniedError as e:
        error_msg = str(e)
        logger.warning(f"Permission denied for CPF {cpf}: {error_msg}")
        raise HTTPException(
            status_code=403,
            detail=error_msg,  # Passar a mensagem específica da PermissionDeniedError
        ) from e
    except Exception as e:
        logger.error(f"❌ Error loading permissions for CPF {cpf}: {e}")
        raise HTTPException(
            status_code=500, detail="Falha ao carregar permissões do usuário"
        ) from e


# Type aliases for dependency injection
CurrentUserPermissions = Annotated[Any, Depends(get_current_user_permissions)]
CurrentUserPermissionsV2 = Annotated[Any, Depends(get_current_user_permissions_v2)]
