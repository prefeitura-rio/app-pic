from abc import ABC, abstractmethod

from src.pic.domain.models.acordo_resultados import AcordoResultados


class IAcordoResultadosRepository(ABC):
    @abstractmethod
    async def get_acordo_resultados(
        self,
        user_token: str | None = None,
        user_id: str | None = None,
        bypass_cache: bool = False,
    ) -> AcordoResultados:
        ...
