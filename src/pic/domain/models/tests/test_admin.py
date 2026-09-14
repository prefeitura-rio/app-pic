from datetime import datetime, timezone

from src.core.security.permissions_models import IdWithName
from src.pic.domain.models.admin import (
    AvailableIds,
    BatchImportError,
    BatchImportResult,
    BatchPermissionsError,
    BatchPermissionsRequest,
    BatchPermissionsResult,
    BatchUserData,
    ImportedUser,
    UpsertUserRequest,
    UserAccessRecord,
)


def test_available_ids_defaults_empty():
    ids = AvailableIds()
    assert ids.cras == []
    assert ids.escolas == []
    assert ids.cres == []
    assert ids.aps == []
    assert ids.cas == []
    assert ids.clinicas == []
    assert ids.equipes_familia == []


def test_available_ids_populated():
    ids = AvailableIds(
        cras=[IdWithName(id="CRAS_001", nome="CRAS Centro")],
        escolas=[IdWithName(id="ESC_001", nome="Escola A")],
        cres=[IdWithName(id="CRE_01", nome="1a CRE")],
    )
    assert len(ids.cras) == 1
    assert ids.cras[0].id == "CRAS_001"
    assert len(ids.escolas) == 1
    assert len(ids.aps) == 0


def test_available_ids_serialization():
    ids = AvailableIds(cras=[IdWithName(id="CRAS_001", nome="CRAS Centro")])
    data = ids.model_dump()
    assert len(data["cras"]) == 1
    assert data["cras"][0]["id"] == "CRAS_001"


def test_user_access_record_minimal():
    now = datetime(2025, 7, 1, tzinfo=timezone.utc)
    uar = UserAccessRecord(cpf="12345678900", created_by="admin", created_at=now)
    assert uar.cpf == "12345678900"
    assert uar.is_admin is False
    assert uar.is_super_admin is False
    assert uar.active is True
    assert uar.created_by == "admin"
    assert uar.created_at == now


def test_user_access_record_full():
    now = datetime(2025, 7, 1, tzinfo=timezone.utc)
    uar = UserAccessRecord(
        cpf="12345678900",
        email="user@example.com",
        nome="Joao",
        ocupacao="Analista",
        secretaria="SMS",
        is_admin=True,
        is_super_admin=False,
        permission="admin",
        id_cras_list=[IdWithName(id="CRAS_001", nome="CRAS Centro")],
        secretaria_acesso="SMS",
        active=True,
        created_by="super_admin",
        created_at=now,
    )
    assert uar.nome == "Joao"
    assert uar.is_admin is True
    assert uar.permission == "admin"
    assert uar.secretaria_acesso == "SMS"
    assert len(uar.id_cras_list) == 1


def test_user_access_record_serialization():
    now = datetime(2025, 7, 1, tzinfo=timezone.utc)
    uar = UserAccessRecord(cpf="11111111111", created_by="admin", created_at=now)
    data = uar.model_dump()
    assert data["cpf"] == "11111111111"
    assert data["is_admin"] is False
    assert data["email"] is None


def test_upsert_user_request_minimal():
    req = UpsertUserRequest()
    assert req.is_admin is False
    assert req.is_super_admin is False
    assert req.active is True
    assert req.is_update is False


def test_upsert_user_request_with_ids():
    req = UpsertUserRequest(
        email="user@example.com",
        is_admin=True,
        id_cras_list=[IdWithName(id="CRAS_001", nome="CRAS Centro")],
        id_escola_list=[IdWithName(id="ESC_001", nome="Escola A")],
        secretaria_acesso="SME",
    )
    assert req.email == "user@example.com"
    assert req.is_admin is True
    assert len(req.id_cras_list) == 1
    assert req.secretaria_acesso == "SME"


def test_batch_import_error():
    e = BatchImportError(row=5, cpf="12345678900", error="CPF invalido")
    assert e.row == 5
    assert e.cpf == "12345678900"
    assert e.error == "CPF invalido"


def test_batch_import_error_default_cpf():
    e = BatchImportError(row=1, error="Arquivo vazio")
    assert e.cpf is None


def test_imported_user_new():
    u = ImportedUser(cpf="12345678900", nome="Joao", status="new")
    assert u.cpf == "12345678900"
    assert u.status == "new"
    assert u.error_message is None
    assert u.is_admin is None


def test_imported_user_exists():
    u = ImportedUser(
        cpf="12345678900",
        status="exists",
        is_admin=True,
        is_super_admin=False,
        secretaria_acesso="SMS",
    )
    assert u.status == "exists"
    assert u.is_admin is True
    assert u.secretaria_acesso == "SMS"


def test_imported_user_error():
    u = ImportedUser(cpf="invalid", status="error", error_message="CPF invalido")
    assert u.status == "error"
    assert u.error_message == "CPF invalido"


def test_batch_import_result():
    result = BatchImportResult(
        total=100,
        imported=80,
        skipped=15,
        errors=[BatchImportError(row=5, error="CPF invalido")],
        imported_users=[
            ImportedUser(cpf="12345678900", status="new"),
            ImportedUser(cpf="98765432100", status="exists", is_admin=True),
        ],
    )
    assert result.total == 100
    assert result.imported == 80
    assert result.skipped == 15
    assert len(result.errors) == 1
    assert len(result.imported_users) == 2


def test_batch_permissions_request():
    req = BatchPermissionsRequest(
        users=[
            BatchUserData(cpf="12345678900", nome="Joao"),
            BatchUserData(cpf="98765432100", nome="Maria"),
        ],
        is_admin=True,
        id_cras_list=[IdWithName(id="CRAS_001", nome="CRAS Centro")],
        secretaria_acesso="SMAS",
    )
    assert len(req.users) == 2
    assert req.users[0].cpf == "12345678900"
    assert req.is_admin is True
    assert req.secretaria_acesso == "SMAS"


def test_batch_permissions_error():
    e = BatchPermissionsError(cpf="12345678900", error="CPF invalido")
    assert e.cpf == "12345678900"
    assert e.error == "CPF invalido"


def test_batch_permissions_result():
    result = BatchPermissionsResult(
        total=50,
        updated=48,
        errors=[BatchPermissionsError(cpf="invalid", error="CPF invalido")],
    )
    assert result.total == 50
    assert result.updated == 48
    assert len(result.errors) == 1
