"""Port do repositório do Painel de Atualizações.

Fonte única: ``endpoint_participante_visao_geral_semanal_protocolos`` no
data-proxy (PostgREST), com RLS aplicada ANTES da agregação — o escopo de
unidades do usuário é respeitado em todas as consultas.

Três consultas (Q1–Q3 da §6 da doc). O repositório devolve linhas ainda não
agregadas; toda a aritmética (taxas, deltas, sanidade da série, lineup,
``tone``) é do use case. ``regiao`` é o valor RAW da coluna da camada na
tabela semanal — o use case o resolve a partir do valor exibido;
``regiao=None`` (e ``camada=None``) roda **sem recorte territorial**: o
escopo vem da RLS do token (painel segue os acessos do usuário).
"""

from abc import ABC, abstractmethod

from src.pic.domain.models.atualizacoes import (
    FocoRow,
    ProtocoloSemanaRow,
    SemanaStatusRow,
)


class IAtualizacoesRepository(ABC):
    @abstractmethod
    async def fetch_semanas_status(
        self,
        camada: str | None,
        regiao: str | None,
        semanas: list[str],
        user_token: str | None = None,
        user_id: str | None = None,
        bypass_cache: bool = False,
    ) -> list[SemanaStatusRow]:
        """Q1 — base + regularidade + série por semana × ``pic_status``.

        ``semanas`` = ISO week-starts (janela de 12 semanas fechadas; a série
        de 5 — W−5..W−1 — é um recorte dela). Linhas ``nivel='geral'`` +
        ``protocolo_secretaria='geral'``.
        """

    @abstractmethod
    async def fetch_protocolos(
        self,
        camada: str | None,
        regiao: str | None,
        semanas: list[str],
        secretarias: list[str] | None = None,
        user_token: str | None = None,
        user_id: str | None = None,
        bypass_cache: bool = False,
    ) -> list[ProtocoloSemanaRow]:
        """Q2 — taxas por protocolo em 2 semanas (``nivel≠'geral'``).

        ``semanas`` = [W−(N+1), W−1]; extremos selecionados no use case por
        Δabs. ``secretarias`` é o filtro de ``protocolo_secretaria``:
        ``None`` = sem filtro (acesso total), ``[]`` = sem acesso a protocolos
        (retorna vazio sem consultar), lista = subset permitido — a RLS
        recorta unidade, não secretaria (§5.3 regra 7).
        """

    @abstractmethod
    async def fetch_foco(
        self,
        camada: str | None,
        regiao: str | None,
        sub_camada: str,
        semanas: list[str],
        user_token: str | None = None,
        user_id: str | None = None,
        bypass_cache: bool = False,
    ) -> list[FocoRow]:
        """Q3 — irregulares por valor da sub-camada nas semanas pedidas.

        ``sub_camada`` ∈ ``regiao_administrativa`` | ``bairro`` (nível do foco
        pelo acesso — regra 6 da §5.3). ``semanas`` = [W−(N+1), W−1] para o
        delta do card; sem comparativo, só [W−1]. O máximo é escolhido no use
        case (PostgREST não ordena por alias agregado).
        """
