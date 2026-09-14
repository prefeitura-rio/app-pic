"""
Simple group-based access control using Authentik groups.
"""

from typing import Annotated, Any, Dict, List

from fastapi import Depends, HTTPException, status

from src.core.security.jwt import verify_jwt


def get_user_groups(token_payload: Dict[str, Any]) -> List[str]:
    """
    Extract user groups from JWT token payload.

    Authentik sends groups in the 'groups' claim as a list of strings.

    Args:
        token_payload: Decoded JWT token payload

    Returns:
        List of group names
    """
    return token_payload.get("groups", [])


def require_groups(*required_groups: str):
    """
    Dependency to require user belongs to specific groups.

    User must belong to at least one of the specified groups.

    Usage:
        @router.get("/admin-only")
        async def admin_endpoint(
            token: Annotated[Dict[str, Any], Depends(require_groups("app-pic-admin"))]
        ):
            return {"message": "Admin access granted"}

        @router.get("/staff")
        async def staff_endpoint(
            token: Annotated[
                Dict[str, Any],
                Depends(require_groups("app-pic-admin", "app-pic-staff"))
            ]
        ):
            return {"message": "Staff access granted"}

    Args:
        *required_groups: Group names - user must belong to at least one

    Returns:
        Dependency function that validates user groups
    """

    async def check_groups(
        token_payload: Annotated[Dict[str, Any], Depends(verify_jwt)]
    ) -> Dict[str, Any]:
        user_groups = get_user_groups(token_payload)

        # Check if user belongs to any of the required groups
        if not any(group in user_groups for group in required_groups):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires membership in one of these groups: {list(required_groups)}",
            )

        return token_payload

    return check_groups


def require_all_groups(*required_groups: str):
    """
    Dependency to require user belongs to ALL specified groups.

    Usage:
        @router.get("/super-admin")
        async def super_admin_endpoint(
            token: Annotated[
                Dict[str, Any],
                Depends(require_all_groups("app-pic-admin", "app-pic-superuser"))
            ]
        ):
            return {"message": "Super admin access granted"}

    Args:
        *required_groups: Group names - user must belong to ALL of them

    Returns:
        Dependency function that validates user has all groups
    """

    async def check_all_groups(
        token_payload: Annotated[Dict[str, Any], Depends(verify_jwt)]
    ) -> Dict[str, Any]:
        user_groups = get_user_groups(token_payload)

        # Check if user belongs to all required groups
        missing_groups = set(required_groups) - set(user_groups)
        if missing_groups:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires membership in all these groups: {list(required_groups)}. Missing: {list(missing_groups)}",
            )

        return token_payload

    return check_all_groups
