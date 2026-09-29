"""Tests for `GetParticipantDetailUseCase` (detail + disparos composition)."""

import pytest

from src.core.security.permissions_models import UserPermissions
from src.pic.application.use_cases.get_participant_detail import (
    GetParticipantDetailUseCase,
)
from src.pic.domain.errors import NotFoundError
from src.pic.domain.models.disparo import Disparo, DisparoMetadados
from src.pic.domain.models.participante import Participante
from src.pic.infrastructure.postgrest_client.errors import PostgrestError

SUPER_ADMIN = UserPermissions(
    cpf="11111111111", is_admin=True, is_super_admin=True, secretarias_acesso=[]
)

REGULAR_USER = UserPermissions(
    cpf="22222222222", is_admin=False, is_super_admin=False, secretarias_acesso=["SMS"]
)


def make_participante() -> Participante:
    return Participante(
        id_familia="02159929700",
        id_membro_familia="00325420412",
        nome="ANA JULIA DE SOUZA DA SILVA",
        cpf="23131727756",
        latitude=-22.867801,
        longitude=-43.2931916,
    )


class FakeParticipantRepository:
    def __init__(self, participante=None, error=None):
        self._participante = participante
        self._error = error
        self.received: dict = {}

    async def get_participant_by_id(
        self, id_membro_familia, permissions=None, user_token=None
    ):
        self.received = {
            "id_membro_familia": id_membro_familia,
            "permissions": permissions,
            "user_token": user_token,
        }
        if self._error:
            raise self._error
        return self._participante


class FakeDisparosRepository:
    def __init__(self, disparos=None):
        self._disparos = disparos
        self.received: dict = {}

    async def get_disparos(self, id_membro_familia, user_token=None):
        self.received = {
            "id_membro_familia": id_membro_familia,
            "user_token": user_token,
        }
        return self._disparos


def make_use_case(participant_repo, disparos_repo) -> GetParticipantDetailUseCase:
    return GetParticipantDetailUseCase(
        repository=participant_repo,
        disparos_repository=disparos_repo,
    )


@pytest.mark.asyncio
async def test_execute_attaches_disparos_to_participant():
    participante = make_participante()
    disparos = [
        Disparo(
            campanha="Mutirão de Vacinação",
            data="2026-07-24",
            datahora="2026-07-25T13:58:52",
            secretaria="SMS",
            status="ENTREGUE",
            indicador_falha=False,
            metadados=DisparoMetadados(
                total_ultimos_30d=3, entregues_30d=3, falhas_30d=0
            ),
        )
    ]
    participant_repo = FakeParticipantRepository(participante)
    disparos_repo = FakeDisparosRepository(disparos)
    use_case = make_use_case(participant_repo, disparos_repo)

    result = await use_case.execute(
        id_membro_familia="00325420412",
        permissions=SUPER_ADMIN,
        user_token="user-jwt",
    )

    assert result.disparos == disparos
    # Both repositories received the same member id and user token.
    assert participant_repo.received["id_membro_familia"] == "00325420412"
    assert disparos_repo.received["id_membro_familia"] == "00325420412"
    assert participant_repo.received["user_token"] == "user-jwt"
    assert disparos_repo.received["user_token"] == "user-jwt"


@pytest.mark.asyncio
async def test_execute_disparos_none_is_graceful():
    participante = make_participante()
    use_case = make_use_case(
        FakeParticipantRepository(participante),
        FakeDisparosRepository(None),
    )

    result = await use_case.execute(
        id_membro_familia="00325420412",
        permissions=SUPER_ADMIN,
        user_token="user-jwt",
    )

    assert result.disparos is None


@pytest.mark.asyncio
async def test_execute_missing_participant_raises_not_found():
    use_case = make_use_case(
        FakeParticipantRepository(None),
        FakeDisparosRepository([]),
    )

    with pytest.raises(NotFoundError):
        await use_case.execute(
            id_membro_familia="missing-id",
            permissions=SUPER_ADMIN,
            user_token="user-jwt",
        )


@pytest.mark.asyncio
async def test_execute_participant_repository_error_propagates():
    use_case = make_use_case(
        FakeParticipantRepository(error=PostgrestError("data-proxy down")),
        FakeDisparosRepository([]),
    )

    with pytest.raises(PostgrestError):
        await use_case.execute(
            id_membro_familia="00325420412",
            permissions=SUPER_ADMIN,
            user_token="user-jwt",
        )


@pytest.mark.asyncio
async def test_execute_non_super_admin_gets_coordinates_cleared():
    participante = make_participante()
    use_case = make_use_case(
        FakeParticipantRepository(participante),
        FakeDisparosRepository([]),
    )

    result = await use_case.execute(
        id_membro_familia="00325420412",
        permissions=REGULAR_USER,
        user_token="user-jwt",
    )

    assert result.latitude is None
    assert result.longitude is None
