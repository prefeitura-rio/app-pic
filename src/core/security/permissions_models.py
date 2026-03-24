"""
Data models for CPF-based data governance.

This module defines the permission models used to control user access
to data based on their assigned facility IDs (CRAS, schools, CRE, etc).
"""
from typing import Optional, List
from pydantic import BaseModel


class IdWithName(BaseModel):
    """ID with name for UI display"""
    id: str
    nome: str


class PermissionDeniedError(Exception):
    """Raised when user doesn't have permission to access data"""
    pass


class UserPermissions(BaseModel):
    """
    User permission record from data_access table.

    Defines which facility IDs a user has access to and their admin status.
    """
    cpf: str
    email: Optional[str] = None
    is_admin: bool = False
    is_super_admin: bool = False
    permission: Optional[str] = None

    # Segmentation lists (None = no restriction for that category)
    id_cras_list: Optional[List[IdWithName]] = None
    id_escola_list: Optional[List[IdWithName]] = None
    id_cre_list: Optional[List[IdWithName]] = None
    id_ap_list: Optional[List[IdWithName]] = None
    id_cas_list: Optional[List[IdWithName]] = None
    id_clinica_familia_list: Optional[List[IdWithName]] = None

    # Protocol access control
    secretaria_acesso: Optional[str] = None  # SME, SMS, SMAS, TODOS, NULL

    active: bool = True
    notes: Optional[str] = None

    def has_full_access(self) -> bool:
        """Super admins have full access to all data"""
        return self.is_super_admin

    def get_filter_ids(self, id_type: str) -> List[str]:
        """
        Get list of IDs for a specific type (e.g., 'id_cras').

        Args:
            id_type: Type of ID ('id_cras', 'id_escola', etc)

        Returns:
            List of ID strings, or empty list if None
        """
        attr_name = f"{id_type}_list"
        id_list = getattr(self, attr_name, None)

        if id_list is None:
            return []

        return [item.id for item in id_list]
