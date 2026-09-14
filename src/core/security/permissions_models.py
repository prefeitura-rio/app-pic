"""
Data models for CPF-based data governance.

This module defines the permission models used to control user access
to data based on their assigned facility IDs (CRAS, schools, CRE, etc).
"""
import logging

from pydantic import BaseModel

from src.pic.domain.models.admin import IdWithName

logger = logging.getLogger(__name__)

_ALL_SECRETARIAS = {"SME", "SMS", "SMAS"}

__all__ = ["IdWithName", "PermissionDeniedError", "UserPermissions"]


class PermissionDeniedError(Exception):
    """Raised when user doesn't have permission to access data"""
    pass


class UserPermissions(BaseModel):
    """
    User permission record loaded from Postgres (users/policy tables).

    Defines which facility IDs a user has access to and their admin status.
    """
    cpf: str
    email: str | None = None
    is_admin: bool = False
    is_super_admin: bool = False
    permission: str | None = None

    # Segmentation lists (None/empty = no restriction for that category)
    id_cras_list: list[IdWithName] | None = None
    id_escola_list: list[IdWithName] | None = None
    id_cre_list: list[IdWithName] | None = None
    id_ap_list: list[IdWithName] | None = None
    id_cas_list: list[IdWithName] | None = None
    id_clinica_familia_list: list[IdWithName] | None = None
    id_equipe_familia_list: list[IdWithName] | None = None

    # Protocol access control: subset of {"SME", "SMS", "SMAS"}.
    # Empty list = no access to protocolo-gated data.
    secretarias_acesso: list[str] = []

    active: bool = True
    notes: str | None = None

    @property
    def secretaria_acesso(self) -> str | None:
        """
        Backward-compat shim for legacy (v1) code that still expects the old
        single-value representation (SME/SMS/SMAS/TODOS/NULL).

        - No secretarias -> None (old "NULL")
        - All three -> "TODOS"
        - Exactly one -> that value
        - Any other combination (2 of 3) has no equivalent in the old model;
          fall back to "TODOS" (permissive) rather than silently dropping
          access, and log so it's visible if this ever triggers.
        """
        if not self.secretarias_acesso:
            return None
        if set(self.secretarias_acesso) >= _ALL_SECRETARIAS:
            return "TODOS"
        if len(self.secretarias_acesso) == 1:
            return self.secretarias_acesso[0]
        logger.warning(
            "secretarias_acesso=%s has no equivalent in the legacy "
            "single-value model; falling back to TODOS for cpf=%s",
            self.secretarias_acesso,
            self.cpf,
        )
        return "TODOS"

    def has_full_access(self) -> bool:
        """Super admins have full access to all data"""
        return self.is_super_admin

    def get_filter_ids(self, id_type: str) -> list[str]:
        """
        Get list of IDs for a specific type (e.g., 'id_cras').

        IMPORTANTE: Expande IDs concatenados (quando múltiplos IDs têm o mesmo nome).
        Ex: IdWithName(id="id1,id2", nome="Escola A") → ["id1", "id2"]

        Args:
            id_type: Type of ID ('id_cras', 'id_escola', etc)

        Returns:
            List of ID strings, or empty list if None
        """
        attr_name = f"{id_type}_list"
        id_list = getattr(self, attr_name, None)

        if id_list is None:
            return []

        # Expandir IDs concatenados (separados por vírgula)
        result = []
        for item in id_list:
            for single_id in item.id.split(","):
                single_id = single_id.strip()
                if single_id:
                    result.append(single_id)

        return result
