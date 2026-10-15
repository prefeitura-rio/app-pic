"""Unit tests for GetAcordoResultadosUseCase.

Covers the access gate (secretaria_acesso != "TODOS" → empty + can_view_acordo
False) and the forwarding of user_token/user_id/bypass_cache to the
repository.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.security.permissions_models import UserPermissions
from src.pic.application.use_cases.get_acordo_resultados import (
    AcordoResultadosOutput,
    GetAcordoResultadosUseCase,
)
from src.pic.domain.models.acordo_resultados import AcordoResultados

SUPER_ADMIN = UserPermissions(
    cpf="12345678900",
    is_admin=True,
    is_super_admin=True,
    secretarias_acesso=["SME", "SMS", "SMAS"],
)

NO_ACCESS = UserPermissions(
    cpf="99999999999",
    is_admin=False,
    is_super_admin=False,
    secretarias_acesso=[],
)

PARTIAL = UserPermissions(
    cpf="88888888888",
    is_admin=False,
    is_super_admin=False,
    secretarias_acesso=["SMS"],
)


def _make_use_case(acordo: AcordoResultados | None = None):
    fake_repo = MagicMock()
    fake_repo.get_acordo_resultados = AsyncMock(
        return_value=acordo or AcordoResultados.empty()
    )
    return GetAcordoResultadosUseCase(repository=fake_repo), fake_repo


@pytest.mark.asyncio
async def test_execute_full_access_returns_data():
    acordo = AcordoResultados(total_participantes=42)
    use_case, fake_repo = _make_use_case(acordo)

    output = await use_case.execute(
        permissions=SUPER_ADMIN,
        user_token="access-token",
        bypass_cache=True,
    )

    assert isinstance(output, AcordoResultadosOutput)
    assert output.can_view_acordo is True
    assert output.data.total_participantes == 42
    fake_repo.get_acordo_resultados.assert_awaited_once_with(
        user_token="access-token",
        user_id="12345678900",
        bypass_cache=True,
    )


@pytest.mark.asyncio
async def test_execute_no_access_returns_empty():
    use_case, fake_repo = _make_use_case()

    output = await use_case.execute(permissions=NO_ACCESS)

    assert output.can_view_acordo is False
    assert output.data.total_participantes == 0
    assert output.data.ativos.total == 0
    assert output.data.protocolos == []
    fake_repo.get_acordo_resultados.assert_not_awaited()


@pytest.mark.asyncio
async def test_execute_partial_access_returns_empty():
    use_case, fake_repo = _make_use_case()

    output = await use_case.execute(permissions=PARTIAL)

    assert output.can_view_acordo is False
    fake_repo.get_acordo_resultados.assert_not_awaited()


@pytest.mark.asyncio
async def test_execute_no_permissions_object():
    use_case, fake_repo = _make_use_case()

    output = await use_case.execute(permissions=None)

    assert output.can_view_acordo is True
    fake_repo.get_acordo_resultados.assert_awaited_once_with(
        user_token=None,
        user_id=None,
        bypass_cache=False,
    )
