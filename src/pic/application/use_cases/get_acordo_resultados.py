from typing import Any

from src.pic.application.ports.acordo_resultados_repository import (
    IAcordoResultadosRepository,
)
from src.pic.domain.models.acordo_resultados import AcordoResultados


class AcordoResultadosOutput:
    def __init__(self, data: AcordoResultados, can_view_acordo: bool = True):
        self.data = data
        self.can_view_acordo = can_view_acordo


class GetAcordoResultadosUseCase:
    def __init__(self, repository: IAcordoResultadosRepository):
        self._repository = repository

    async def execute(
        self,
        permissions: Any,
        user_token: str | None = None,
        bypass_cache: bool = False,
    ) -> AcordoResultadosOutput:
        if permissions and permissions.secretaria_acesso != "TODOS":
            return AcordoResultadosOutput(
                data=AcordoResultados.empty(),
                can_view_acordo=False,
            )

        acordo = await self._repository.get_acordo_resultados(
            user_token=user_token,
            user_id=permissions.cpf if permissions else None,
            bypass_cache=bypass_cache,
        )

        return AcordoResultadosOutput(data=acordo)
