"""Contexto por requisição para propagação do token Keycloak até o PostgREST.

O token do usuário autenticado é armazenado em um ContextVar, isolado por
task asyncio. Nunca há vazamento entre requisições concorrentes.

Atenção: tasks filhas (asyncio.create_task) herdam o contexto da task pai.
Jobs em background que não devem usar o token do usuário precisam chamar
clear_postgrest_token() no início ou usar o contexto with_service_token().
"""

from contextvars import ContextVar, Token

postgrest_token: ContextVar[str | None] = ContextVar("postgrest_token", default=None)


def get_postgrest_token() -> str | None:
    """Retorna o token do usuário autenticado no contexto atual, se houver."""
    return postgrest_token.get()


def set_postgrest_token(token: str) -> None:
    """Armazena o token do usuário no contexto da task atual."""
    postgrest_token.set(token)


def clear_postgrest_token() -> None:
    """Remove o token do contexto atual.

    Deve ser chamado no início de tasks filhas que não devem herdar o
    token do usuário (ex.: jobs em background).
    """
    postgrest_token.set(None)


class _ServiceTokenContext:
    """Bloqueia o token de usuário no bloco, forçando o fallback de serviço."""

    _token: Token[str | None]

    def __enter__(self) -> None:
        self._token = postgrest_token.set(None)

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        postgrest_token.reset(self._token)


def with_service_token() -> _ServiceTokenContext:
    """Retorna um contexto que força o fallback de token de serviço."""
    return _ServiceTokenContext()
