from typing import Any

from src.core.security.permissions_models import UserPermissions

GOLD_LEVEL = "ouro"


def team_permissions(
    token_payload: dict[str, Any], group: str, require_gold: bool = True
) -> UserPermissions | None:
    cpf = token_payload.get("preferred_username")
    groups = token_payload.get("groups") or []
    if isinstance(groups, str):
        groups = [groups]
    if not cpf or group not in groups:
        return None
    if require_gold and token_payload.get("reliability_level") != GOLD_LEVEL:
        return None
    return UserPermissions(
        cpf=cpf,
        is_admin=True,
        is_super_admin=True,
        permission="super_admin",
        # Acesso total por secretaria: sem isso o gate do dashboard/acordo
        # (secretaria_acesso != "TODOS" → vazio) zeraria a visão dos super
        # admins que entram pelo grupo.
        secretarias_acesso=["SME", "SMS", "SMAS"],
    )
