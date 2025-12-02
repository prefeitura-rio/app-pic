"""
Example endpoints demonstrating group-based access control.
"""

from typing import Annotated, Any, Dict

from fastapi import APIRouter, Depends

from src.core.security.jwt import verify_jwt
from src.core.security.permissions import (
    get_user_groups,
    require_all_groups,
    require_groups,
)

router = APIRouter(prefix="/examples", tags=["Examples"])


@router.get("/public")
async def public_endpoint():
    """Public endpoint - no authentication required."""
    return {"message": "This endpoint is public"}


@router.get("/authenticated")
async def authenticated_endpoint(
    token_payload: Annotated[Dict[str, Any], Depends(verify_jwt)]
):
    """Authenticated endpoint - requires valid JWT only."""
    return {
        "message": "You are authenticated",
        "user": token_payload.get("preferred_username"),
        "email": token_payload.get("email"),
        "groups": get_user_groups(token_payload),
    }


@router.get("/admin-only")
async def admin_only_endpoint(
    token_payload: Annotated[
        Dict[str, Any], Depends(require_groups("app-pic-admin"))
    ]
):
    """Endpoint requiring membership in 'app-pic-admin' group."""
    return {
        "message": "Admin access granted",
        "user": token_payload.get("preferred_username"),
        "groups": get_user_groups(token_payload),
    }


@router.get("/staff")
async def staff_endpoint(
    token_payload: Annotated[
        Dict[str, Any], Depends(require_groups("app-pic-admin", "app-pic-staff"))
    ]
):
    """Endpoint requiring membership in 'app-pic-admin' OR 'app-pic-staff' group."""
    return {
        "message": "Staff access granted",
        "user": token_payload.get("preferred_username"),
        "groups": get_user_groups(token_payload),
    }


@router.get("/super-admin")
async def super_admin_endpoint(
    token_payload: Annotated[
        Dict[str, Any],
        Depends(require_all_groups("app-pic-admin", "app-pic-superuser")),
    ]
):
    """Endpoint requiring membership in BOTH 'app-pic-admin' AND 'app-pic-superuser' groups."""
    return {
        "message": "Super admin access granted",
        "user": token_payload.get("preferred_username"),
        "groups": get_user_groups(token_payload),
    }


@router.get("/me")
async def get_current_user(
    token_payload: Annotated[Dict[str, Any], Depends(verify_jwt)]
):
    """Get current user information including groups from Authentik."""
    return {
        "user": {
            "sub": token_payload.get("sub"),
            "email": token_payload.get("email"),
            "preferred_username": token_payload.get("preferred_username"),
            "name": token_payload.get("name"),
        },
        "groups": get_user_groups(token_payload),
        "all_claims": token_payload,
    }
