from datetime import datetime

from pydantic import BaseModel, Field


class IdWithName(BaseModel):
    """ID with name for UI display.

    Canonical domain model; `src.core.security.permissions_models` re-exports
    this class so legacy consumers keep importing from there.
    """

    id: str
    nome: str


# public available-ids endpoint type -> (policy unit_type, permissions attr)
UNIT_TYPE_REGISTRY: dict[str, tuple[str, str]] = {
    "cras": ("cras", "id_cras_list"),
    "escolas": ("escola", "id_escola_list"),
    "cres": ("cre", "id_cre_list"),
    "aps": ("ap", "id_ap_list"),
    "cas": ("cas", "id_cas_list"),
    "clinicas": ("clinica_familia", "id_clinica_familia_list"),
    "equipes_familia": ("equipe_familia", "id_equipe_familia_list"),
}


def calculate_permission(is_admin: bool, is_super_admin: bool) -> str:
    if is_super_admin:
        return "super_admin"
    elif is_admin:
        return "admin"
    else:
        return "user"


class UserAccessRecord(BaseModel):
    cpf: str
    email: str | None = None
    nome: str | None = None
    ocupacao: str | None = None
    secretaria: str | None = None
    is_admin: bool = False
    is_super_admin: bool = False
    permission: str | None = None

    id_cras_list: list[IdWithName] | None = None
    id_escola_list: list[IdWithName] | None = None
    id_cre_list: list[IdWithName] | None = None
    id_ap_list: list[IdWithName] | None = None
    id_cas_list: list[IdWithName] | None = None
    id_clinica_familia_list: list[IdWithName] | None = None
    id_equipe_familia_list: list[IdWithName] | None = None

    secretarias_acesso: list[str] = Field(default_factory=list)

    active: bool = True
    notes: str | None = None
    created_by: str
    created_at: datetime
    updated_by: str | None = None
    updated_at: datetime | None = None


class UpsertUserRequest(BaseModel):
    email: str | None = None
    nome: str | None = None
    ocupacao: str | None = None
    secretaria: str | None = None
    is_admin: bool = False
    is_super_admin: bool = False

    id_cras_list: list[IdWithName] | None = None
    id_escola_list: list[IdWithName] | None = None
    id_cre_list: list[IdWithName] | None = None
    id_ap_list: list[IdWithName] | None = None
    id_cas_list: list[IdWithName] | None = None
    id_clinica_familia_list: list[IdWithName] | None = None
    id_equipe_familia_list: list[IdWithName] | None = None

    secretarias_acesso: list[str] | None = None

    notes: str | None = None
    active: bool = True
    is_update: bool = False


class BatchImportError(BaseModel):
    row: int
    cpf: str | None = None
    error: str


class ImportedUser(BaseModel):
    cpf: str
    nome: str | None = None
    email: str | None = None
    ocupacao: str | None = None
    secretaria: str | None = None
    status: str
    error_message: str | None = None

    is_admin: bool | None = None
    is_super_admin: bool | None = None
    id_cras_list: list[IdWithName] | None = None
    id_escola_list: list[IdWithName] | None = None
    id_cre_list: list[IdWithName] | None = None
    id_ap_list: list[IdWithName] | None = None
    id_cas_list: list[IdWithName] | None = None
    id_clinica_familia_list: list[IdWithName] | None = None
    id_equipe_familia_list: list[IdWithName] | None = None
    secretarias_acesso: list[str] | None = None


class BatchImportResult(BaseModel):
    total: int
    imported: int
    skipped: int
    errors: list[BatchImportError]
    imported_users: list[ImportedUser]


class BatchUserData(BaseModel):
    cpf: str
    nome: str | None = None
    email: str | None = None
    ocupacao: str | None = None
    secretaria: str | None = None


class BatchPermissionsRequest(BaseModel):
    users: list[BatchUserData]
    is_admin: bool = False
    id_cras_list: list[IdWithName] | None = None
    id_escola_list: list[IdWithName] | None = None
    id_cre_list: list[IdWithName] | None = None
    id_ap_list: list[IdWithName] | None = None
    id_cas_list: list[IdWithName] | None = None
    id_clinica_familia_list: list[IdWithName] | None = None
    id_equipe_familia_list: list[IdWithName] | None = None
    secretarias_acesso: list[str] | None = None


class BatchPermissionsError(BaseModel):
    cpf: str
    error: str


class BatchPermissionsResult(BaseModel):
    total: int
    updated: int
    errors: list[BatchPermissionsError]
