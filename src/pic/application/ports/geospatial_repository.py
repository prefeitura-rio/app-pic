from abc import ABC, abstractmethod

from src.pic.domain.models.filters import FilterOption
from src.pic.domain.models.geospatial import (
    CamadaRegularidadeAggregate,
    GeospatialFilterOptions,
    GeospatialLayer,
    ProtocoloOption,
    RegiaoProtocoloAggregate,
    RegiaoRegularidadeResumo,
)


class IGeospatialRepository(ABC):
    @abstractmethod
    async def fetch_layers(
        self,
        column_filters: dict[str, object],
        user_token: str | None = None,
        bypass_cache: bool = False,
    ) -> list[GeospatialLayer]:
        ...

    @abstractmethod
    async def fetch_regularidade_por_camada(
        self,
        camada: str,
        user_token: str | None = None,
        user_id: str | None = None,
        bypass_cache: bool = False,
        status: list[str] | None = None,
        cohortes: list[str] | None = None,
        protocolo_id: str | None = None,
    ) -> list[CamadaRegularidadeAggregate]:
        """Regularidade agregada por região da camada (RLS aplicada pelo PostgREST).

        ``camada`` define a coluna do GROUP BY no consolidado (ver
        ``CAMADA_GROUP_COLUMN``): ``"bairro"``, ``"ra"``, ``"cas"``, ``"cre"``
        ou ``"ap"``.

        Filtros opcionais (multiselect — mesmo padrão da Visão Geral):
        - ``status``: lista de ``"Ativo"``/``"Inativo"`` → ``pic_status=in.(...)``
        - ``cohortes``: lista de meses ``"YYYY-MM-DD"`` → ``pic_cohort=in.(...)``
        - ``protocolo_id``: troca a fonte para a visão geral de protocolos
          (métrica ``protocolo_regular_*`` daquele protocolo — FR-007)
        """

    @abstractmethod
    async def fetch_protocolos(
        self,
        user_token: str | None = None,
        user_id: str | None = None,
        bypass_cache: bool = False,
    ) -> list[ProtocoloOption]:
        """Vocabulário de protocolos disponíveis (com RLS do usuário)."""

    @abstractmethod
    async def fetch_protocolos_por_regiao(
        self,
        camada: str,
        regiao: str,
        user_token: str | None = None,
        user_id: str | None = None,
        bypass_cache: bool = False,
        status: list[str] | None = None,
        cohortes: list[str] | None = None,
    ) -> list[RegiaoProtocoloAggregate]:
        """Métrica de TODOS os protocolos numa região da camada (fase 3j).

        ``regiao`` é o valor RAW da coluna da camada no consolidado (ex.:
        ``"3ª Rio Comprido"`` para RA) — o use case o descobre pelos
        agregados gerais e repassa aqui para filtrar com ``eq`` no PostgREST
        (consulta pequena, ≤ número de protocolos). Filtros ``status``/
        ``cohortes`` aplicados como no restante do geospatial.
        """

    @abstractmethod
    async def fetch_protocolo_geral(
        self,
        protocolo_id: str,
        user_token: str | None = None,
        user_id: str | None = None,
        bypass_cache: bool = False,
        status: list[str] | None = None,
        cohortes: list[str] | None = None,
    ) -> RegiaoRegularidadeResumo | None:
        """Métrica de um protocolo em TODAS as regiões (fase 3k).

        Agrega a visão geral de protocolos sem filtro de região (``eq`` no
        ``protocolo_id`` + filtros ``status``/``cohortes``) — o valor é o
        MESMO para qualquer região, então o cache é compartilhado entre
        cliques. Usado no comparativo "acima/abaixo da média geral".
        """

    @abstractmethod
    async def get_filter_options(
        self,
        field: str,
        column_filters: dict[str, object] | None = None,
        user_token: str | None = None,
        bypass_cache: bool = False,
    ) -> list[FilterOption]:
        """Return distinct non-null values for *field* (lazy, per-field vocab)."""
        ...

    @abstractmethod
    async def get_filter_vocabulary(
        self,
        user_token: str | None = None,
        bypass_cache: bool = False,
    ) -> GeospatialFilterOptions:
        """Return the full filter vocabulary (all fields, backward compat)."""
        ...
