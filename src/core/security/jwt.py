import httpx
import jwt
from fastapi import HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from typing import Dict, Any
from src.config import env
from src.utils.log import logger

security = HTTPBearer()

# Cache for JWKS keys
_jwks_cache: Dict[str, Any] = {}


async def get_jwks() -> Dict[str, Any]:
    """Fetch JWKS from Authentik and cache it."""
    if _jwks_cache:
        return _jwks_cache

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(env.AUTHENTIK_JWKS_URL)
            response.raise_for_status()
            jwks = response.json()
            _jwks_cache.update(jwks)
            return jwks
    except Exception as e:
        logger.error(f"Failed to fetch JWKS: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch JWKS")


def get_signing_key(token: str, jwks: Dict[str, Any]) -> Any:
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
        logger.error(f"Error getting signing key: {e}")
        raise HTTPException(status_code=401, detail="Invalid token header")


async def verify_jwt(
    credentials: HTTPAuthorizationCredentials = Security(security),
) -> Dict[str, Any]:
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
            audience=env.AUTHENTIK_AUDIENCE,
            issuer=env.AUTHENTIK_ISSUER,
        )

        logger.info(f"Token verified for user: {payload.get('sub')}")
        return payload

    except jwt.ExpiredSignatureError:
        logger.warning("Token has expired")
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.InvalidAudienceError:
        logger.warning("Invalid token audience")
        raise HTTPException(status_code=401, detail="Invalid token audience")
    except jwt.InvalidIssuerError:
        logger.warning("Invalid token issuer")
        raise HTTPException(status_code=401, detail="Invalid token issuer")
    except jwt.InvalidTokenError as e:
        logger.warning(f"Invalid token: {e}")
        raise HTTPException(status_code=401, detail="Invalid token")
    except Exception as e:
        logger.error(f"Token verification failed: {e}")
        raise HTTPException(status_code=401, detail="Could not validate credentials")
