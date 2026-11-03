"""Testes do gate de acesso do dashboard (secretaria_acesso × super admin).

O gate original devolvia dashboard vazio para qualquer permissão que não
fosse "TODOS" — incluindo super admins (ex.: grupo pic) cujas permissões
chegam com `secretarias_acesso=[]`. O bypass por `is_super_admin` cobre
esse caso sem afrouxar o gate dos demais usuários.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.security.permissions_models import UserPermissions
from src.pic.application.use_cases.get_dashboard import GetDashboardUseCase


def _make_use_case():
    fake_repo = MagicMock()
    fake_repo.get_dashboard_metrics = AsyncMock(return_value=MagicMock())
    return GetDashboardUseCase(repository=fake_repo), fake_repo


def _perms(secretarias: list[str] | None = None, is_super_admin: bool = False):
    return UserPermissions(
        cpf="12345678900",
        secretarias_acesso=secretarias or [],
        is_admin=is_super_admin,
        is_super_admin=is_super_admin,
    )


@pytest.mark.asyncio
async def test_super_admin_com_secretarias_vazias_acessa_dashboard():
    use_case, fake_repo = _make_use_case()

    output = await use_case.execute(
        permissions=_perms(is_super_admin=True), user_token="jwt"
    )

    assert output.can_view_dashboard is True
    fake_repo.get_dashboard_metrics.assert_awaited_once()


@pytest.mark.asyncio
async def test_usuario_com_secretaria_unica_nao_acessa():
    use_case, fake_repo = _make_use_case()

    output = await use_case.execute(
        permissions=_perms(secretarias=["SMS"]), user_token="jwt"
    )

    assert output.can_view_dashboard is False
    fake_repo.get_dashboard_metrics.assert_not_awaited()


@pytest.mark.asyncio
async def test_todas_as_secretarias_acessa():
    use_case, fake_repo = _make_use_case()

    output = await use_case.execute(
        permissions=_perms(secretarias=["SME", "SMS", "SMAS"]), user_token="jwt"
    )

    assert output.can_view_dashboard is True
    fake_repo.get_dashboard_metrics.assert_awaited_once()
