from fastapi import APIRouter, Depends
from typing import Dict, Any
from src.core.security.jwt import verify_jwt

router = APIRouter()


@router.get("/protected")
async def protected_route(token_payload: Dict[str, Any] = Depends(verify_jwt)):
    """
    Protected endpoint that requires JWT authentication.
    Returns user information from the JWT token.
    """
    return {
        "message": "Successfully authenticated!",
        "user": {
            "sub": token_payload.get("sub"),
            "email": token_payload.get("email"),
            "preferred_username": token_payload.get("preferred_username"),
            "name": token_payload.get("name"),
        },
        "token_info": {
            "iss": token_payload.get("iss"),
            "aud": token_payload.get("aud"),
            "exp": token_payload.get("exp"),
            "iat": token_payload.get("iat"),
        },
    }
