from datetime import UTC, datetime
from unittest.mock import AsyncMock

import polars as pl
import pytest

from src.core.security.permissions_models import UserPermissions
from src.pic.application.use_cases.admin.write import UpsertUserUseCase
from src.pic.domain.errors import ForbiddenError
from src.pic.domain.models.admin import UpsertUserRequest

TARGET = "11122233344"


def make_repo() -> AsyncMock:
    repo = AsyncMock()
    repo.fetch_governance_df.return_value = (pl.DataFrame({"cpf": []}), False, None)
    repo.fetch_user_record.return_value = {
        "cpf": TARGET,
        "created_by": "99988877766",
        "created_at": datetime(2026, 1, 1, tzinfo=UTC).isoformat(),
    }
    return repo


def make_actor(is_super_admin: bool) -> UserPermissions:
    return UserPermissions(
        cpf="99988877766",
        is_admin=True,
        is_super_admin=is_super_admin,
        secretarias_acesso=["SME", "SMS", "SMAS"],
    )


async def test_super_admin_grants_the_general_view():
    repo = make_repo()

    await UpsertUserUseCase(repo).execute(
        make_actor(True), TARGET, UpsertUserRequest(nome="Ana", general_view=True)
    )

    assert repo.insert_user.await_args.kwargs["fields"]["general_view"] is True


async def test_super_admin_revokes_the_general_view():
    repo = make_repo()

    await UpsertUserUseCase(repo).execute(
        make_actor(True), TARGET, UpsertUserRequest(nome="Ana", general_view=False)
    )

    assert repo.insert_user.await_args.kwargs["fields"]["general_view"] is False


async def test_admin_that_is_not_super_admin_cannot_set_the_general_view():
    repo = make_repo()

    with pytest.raises(ForbiddenError):
        await UpsertUserUseCase(repo).execute(
            make_actor(False), TARGET, UpsertUserRequest(nome="Ana", general_view=True)
        )

    repo.insert_user.assert_not_awaited()
    repo.update_user.assert_not_awaited()


async def test_a_request_without_the_field_leaves_the_general_view_alone():
    repo = make_repo()

    await UpsertUserUseCase(repo).execute(
        make_actor(False), TARGET, UpsertUserRequest(nome="Ana")
    )

    assert "general_view" not in repo.insert_user.await_args.kwargs["fields"]
