from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from src.core.security.jwt import get_current_user_permissions, verify_jwt
from src.core.security.permissions_models import IdWithName, UserPermissions
from src.main import app
from src.pic.domain.models.admin import (
    AvailableIds,
    BatchImportResult,
    BatchPermissionsResult,
    UpsertUserRequest,
    UserAccessRecord,
)


@pytest.fixture
def override_auth():
    token_payload = {"preferred_username": "12345678900"}
    app.dependency_overrides[verify_jwt] = lambda: token_payload
    app.dependency_overrides[get_current_user_permissions] = lambda: UserPermissions(
        cpf="12345678900",
        is_admin=True,
        is_super_admin=True,
        secretaria_acesso="TODOS",
    )
    yield
    app.dependency_overrides.clear()


@pytest.fixture
async def client(override_auth):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


def _make_user_record() -> UserAccessRecord:
    return UserAccessRecord(
        cpf="12345678900",
        email="admin@example.com",
        nome="Admin User",
        is_admin=True,
        is_super_admin=True,
        permission="super_admin",
        secretaria_acesso="TODOS",
        active=True,
        created_by="system",
        created_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
    )


class TestAdminMe:
    @pytest.mark.asyncio
    async def test_get_me_200(self, client):
        with patch(
            "src.pic.presentation.v2.admin.get_current_user_info",
            return_value=_make_user_record(),
        ):
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
        mock_ids = AvailableIds(
            cras=[IdWithName(id="CRAS_001", nome="CRAS Centro")],
            escolas=[IdWithName(id="ESC_001", nome="Escola A")],
        )
        with patch(
            "src.pic.presentation.v2.admin.get_available_ids_data",
            new_callable=AsyncMock,
            return_value=mock_ids,
        ):
            response = await client.get("/api/v2/admin/available-ids")
            assert response.status_code == 200
            body = response.json()
            assert len(body["cras"]) == 1
            assert body["cras"][0]["id"] == "CRAS_001"


class TestAdminListUsers:
    @pytest.mark.asyncio
    async def test_list_users_200(self, client):
        mock_users = [_make_user_record()]
        from src.api.v1.schemas import PaginationMeta
        mock_meta = PaginationMeta(
            page=1, page_size=20, total_rows=1, total_pages=1, cache_hit=True
        )

        with patch(
            "src.pic.presentation.v2.admin.list_users_data",
            new_callable=AsyncMock,
            return_value=(mock_users, mock_meta, None),
        ):
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
        with patch(
            "src.pic.presentation.v2.admin.upsert_user_data",
            new_callable=AsyncMock,
            return_value=user,
        ):
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
        with patch(
            "src.pic.presentation.v2.admin.delete_user_data",
            new_callable=AsyncMock,
            return_value=None,
        ):
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
        with patch(
            "src.pic.presentation.v2.admin.batch_import_users_data",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
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
        with patch(
            "src.pic.presentation.v2.admin.batch_update_permissions_data",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
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
