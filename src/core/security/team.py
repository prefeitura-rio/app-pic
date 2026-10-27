from typing import Any

from src.core.security.permissions_models import UserPermissions

GOLD_LEVEL = "ouro"


def team_permissions(
    token_payload: dict[str, Any], group: str
) -> UserPermissions | None:
    cpf = token_payload.get("preferred_username")
    groups = token_payload.get("groups") or []
    if isinstance(groups, str):
        groups = [groups]
    if not cpf or group not in groups:
        return None
    if token_payload.get("reliability_level") != GOLD_LEVEL:
        return None
    return UserPermissions(
        cpf=cpf, is_admin=True, is_super_admin=True, permission="super_admin"
    )
