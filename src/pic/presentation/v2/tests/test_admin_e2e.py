from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from src.core.security.jwt import get_current_user_permissions_v2, verify_jwt
from src.core.security.permissions_models import IdWithName, UserPermissions
from src.main import app
from src.pic.application.use_cases.admin.batch import (
    BatchImportUsersUseCase,
    BatchUpdatePermissionsUseCase,
)
from src.pic.application.use_cases.admin.read import (
    GetAvailableUnitIdsUseCase,
    GetCurrentUserUseCase,
)
from src.pic.application.use_cases.admin.write import (
    DeleteUserUseCase,
    ListUsersUseCase,
    UpsertUserUseCase,
)
from src.pic.domain.models.admin import (
    BatchImportResult,
    BatchPermissionsResult,
    UserAccessRecord,
)
from src.pic.domain.models.pagination import PaginationMeta
from src.pic.presentation.di import (
    get_available_unit_ids_use_case,
    get_batch_import_users_use_case,
    get_batch_update_permissions_use_case,
    get_current_user_use_case,
    get_delete_user_use_case,
    get_list_users_use_case,
    get_upsert_user_use_case,
)


@pytest.fixture
def override_auth():
    token_payload = {"preferred_username": "12345678900"}
    app.dependency_overrides[verify_jwt] = lambda: token_payload
    app.dependency_overrides[get_current_user_permissions_v2] = lambda: UserPermissions(
        cpf="12345678900",
        is_admin=True,
        is_super_admin=True,
        secretarias_acesso=["SME", "SMS", "SMAS"],
    )
    yield
    app.dependency_overrides.clear()


@pytest.fixture
async def client(override_auth):
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={
            "Authorization": "Bearer fake-jwt-token",
            "X-Access-Token": "fake-access-token",
        },
    ) as ac:
        yield ac


def _make_user_record() -> UserAccessRecord:
    return UserAccessRecord(
        cpf="12345678900",
        email="admin@example.com",
        nome="Admin User",
        is_admin=True,
        is_super_admin=True,
        permission="super_admin",
        secretarias_acesso=["SME", "SMS", "SMAS"],
        active=True,
        created_by="system",
        created_at=datetime(2025, 1, 1, tzinfo=UTC),
    )


class TestAdminMe:
    @pytest.mark.asyncio
    async def test_get_me_200(self, client):

        def _override_use_case():
            uc = MagicMock(spec=GetCurrentUserUseCase)
            uc.execute.return_value = _make_user_record()
            return uc

        app.dependency_overrides[get_current_user_use_case] = _override_use_case

        response = await client.get("/api/v2/admin/me")
        assert response.status_code == 200
        body = response.json()
        assert body["cpf"] == "12345678900"
        assert body["is_admin"] is True
        assert body["permission"] == "super_admin"

    @pytest.mark.asyncio
    async def test_get_me_401(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            response = await c.get("/api/v2/admin/me")
            assert response.status_code == 401


class TestAdminAvailableIds:
    @pytest.mark.asyncio
    async def test_get_available_ids_200(self, client):
        mock_ids = [IdWithName(id="CRAS_001", nome="CRAS Centro")]

        def _override_use_case():
            uc = MagicMock(spec=GetAvailableUnitIdsUseCase)
            uc.execute = AsyncMock(return_value=mock_ids)
            return uc

        app.dependency_overrides[get_available_unit_ids_use_case] = _override_use_case

        response = await client.get("/api/v2/admin/available-ids/cras")
        assert response.status_code == 200
        body = response.json()
        assert len(body) == 1
        assert body[0]["id"] == "CRAS_001"
        assert body[0]["nome"] == "CRAS Centro"

    @pytest.mark.asyncio
    async def test_get_available_ids_invalid_unit_type_422(self, client):
        response = await client.get("/api/v2/admin/available-ids/invalido")
        assert response.status_code == 422


class TestAdminListUsers:
    @pytest.mark.asyncio
    async def test_list_users_200(self, client):
        mock_users = [_make_user_record()]
        mock_meta = PaginationMeta(
            page=1, page_size=20, total_rows=1, total_pages=1, cache_hit=True
        )

        def _override_use_case():
            uc = MagicMock(spec=ListUsersUseCase)
            uc.execute = AsyncMock(return_value=(mock_users, mock_meta, None))
            return uc

        app.dependency_overrides[get_list_users_use_case] = _override_use_case

        response = await client.get("/api/v2/admin/users?page=1&page_size=20")
        assert response.status_code == 200
        body = response.json()
        assert body["meta"]["page"] == 1
        assert body["meta"]["total_rows"] == 1
        assert len(body["data"]) == 1
        assert body["data"][0]["cpf"] == "12345678900"

    @pytest.mark.asyncio
    async def test_list_users_422_invalid_page(self, client):
        response = await client.get("/api/v2/admin/users?page=0&page_size=20")
        assert response.status_code == 422


class TestAdminUpsertUser:
    @pytest.mark.asyncio
    async def test_upsert_user_200(self, client):
        user = _make_user_record()

        def _override_use_case():
            uc = MagicMock(spec=UpsertUserUseCase)
            uc.execute = AsyncMock(return_value=user)
            return uc

        app.dependency_overrides[get_upsert_user_use_case] = _override_use_case

        response = await client.put(
            "/api/v2/admin/users/12345678900",
            json={"is_admin": True, "active": True},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["cpf"] == "12345678900"

    @pytest.mark.asyncio
    async def test_upsert_user_422_invalid_cpf(self, client):
        response = await client.put(
            "/api/v2/admin/users/abc",
            json={"active": True},
        )
        assert response.status_code == 422


class TestAdminDeleteUser:
    @pytest.mark.asyncio
    async def test_delete_user_204(self, client):

        def _override_use_case():
            uc = MagicMock(spec=DeleteUserUseCase)
            uc.execute = AsyncMock(return_value=None)
            return uc

        app.dependency_overrides[get_delete_user_use_case] = _override_use_case

        response = await client.delete("/api/v2/admin/users/12345678900")
        assert response.status_code == 204

    @pytest.mark.asyncio
    async def test_delete_user_422_invalid_cpf(self, client):
        response = await client.delete("/api/v2/admin/users/abc")
        assert response.status_code == 422


class TestAdminBatchImport:
    @pytest.mark.asyncio
    async def test_batch_import_200(self, client):
        mock_result = BatchImportResult(
            total=10,
            imported=8,
            skipped=2,
            errors=[],
            imported_users=[],
        )

        def _override_use_case():
            uc = MagicMock(spec=BatchImportUsersUseCase)
            uc.execute = AsyncMock(return_value=mock_result)
            return uc

        app.dependency_overrides[get_batch_import_users_use_case] = _override_use_case

        response = await client.post(
            "/api/v2/admin/users-batch",
            files={"file": ("test.csv", b"cpf\n12345678900", "text/csv")},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 10
        assert body["imported"] == 8


class TestAdminBatchPermissions:
    @pytest.mark.asyncio
    async def test_batch_permissions_200(self, client):
        mock_result = BatchPermissionsResult(total=10, updated=9, errors=[])

        def _override_use_case():
            uc = MagicMock(spec=BatchUpdatePermissionsUseCase)
            uc.execute = AsyncMock(return_value=mock_result)
            return uc

        app.dependency_overrides[get_batch_update_permissions_use_case] = _override_use_case

        response = await client.put(
            "/api/v2/admin/users-batch/permissions",
            json={
                "users": [{"cpf": "12345678900", "nome": "Test"}],
                "is_admin": True,
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 10
        assert body["updated"] == 9
