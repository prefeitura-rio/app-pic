"""Wrapper assíncrono do client PostgREST com token por requisição."""

from typing import Any

import httpx
from postgrest import AsyncPostgrestClient
from postgrest.exceptions import APIError

from src.pic.infrastructure.postgrest_client.auth import PostgrestJwtAuth
from src.pic.infrastructure.postgrest_client.request_context import get_postgrest_token
from src.utils.log import logger


class PostgrestAPIError(Exception):
    """Erro de API do PostgREST traduzido para o domínio da aplicação."""

    def __init__(
        self,
        *,
        code: str | None,
        message: str | None,
        details: str | None = None,
        hint: str | None = None,
    ) -> None:
        self.code = code
        self.message = message
        self.details = details
        self.hint = hint
        super().__init__(message or code or "PostgREST API error")

    @classmethod
    def from_api_error(cls, error: APIError) -> "PostgrestAPIError":
        return cls(
            code=error.code,
            message=error.message,
            details=error.details,
            hint=error.hint,
        )


class PostgrestAuthError(Exception):
    """Nenhum token disponível para autenticar a chamada no PostgREST."""


class PostgrestClient:
    """Client PostgREST assíncrono com token resolvido por requisição.

    O token segue a prioridade:

    1. Token Keycloak do usuário autenticado (ContextVar, setado no
       ``verify_jwt``). Encaminhado tal qual ao PostgREST.
    2. Token de serviço auto-assinado (``PostgrestJwtAuth``), para jobs em
       background sem usuário.
    3. Sem nenhum dos dois, ``PostgrestAuthError``.

    Mantém um pool de conexões httpx compartilhado. Pode receber um
    ``http_client`` customizado (ex.: com MockTransport) para testes.

    IMPORTANTE: a aplicação do token e a criação do builder acontecem num
    bloco síncrono sem ``await``, o que garante atomicidade por task mesmo
    com o pool compartilhado. Não introduza pontos de espera nesse trecho.
    """

    def __init__(
        self,
        url: str,
        *,
        schema: str,
        auth: PostgrestJwtAuth | None = None,
        timeout_seconds: float = 30.0,
        max_connections: int = 50,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._auth = auth
        self._owns_session = http_client is None
        session = http_client or httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_seconds),
            limits=httpx.Limits(
                max_connections=max_connections,
                max_keepalive_connections=max(10, max_connections // 2),
            ),
            follow_redirects=True,
        )
        self._client = AsyncPostgrestClient(url, schema=schema, http_client=session)

    @property
    def session(self) -> httpx.AsyncClient:
        return self._client.session

    def _resolve_token(self) -> str:
        token = get_postgrest_token()
        if token is None and self._auth is not None:
            token = self._auth.get_token()
        if token is None:
            raise PostgrestAuthError(
                "Nenhum token disponível para o PostgREST: "
                "sem token de usuário no contexto e sem token de serviço configurado"
            )
        return token

    def _apply_auth(self) -> None:
        self._client.auth(self._resolve_token())

    def table(self, table: str):
        """Constrói uma operação sobre a tabela informada."""
        self._apply_auth()
        return self._client.table(table)

    def from_(self, table: str):
        return self.table(table)

    def rpc(
        self,
        func: str,
        params: dict[str, Any],
        *,
        count: Any = None,
        head: bool = False,
        get: bool = False,
    ):
        """Chama uma stored procedure via /rpc."""
        self._apply_auth()
        return self._client.rpc(func, params, count=count, head=head, get=get)

    async def execute(self, builder: Any) -> Any:
        """Executa um query builder traduzindo APIError para PostgrestAPIError."""
        try:
            return await builder.execute()
        except APIError as error:
            mapped = PostgrestAPIError.from_api_error(error)
            logger.error(
                "PostgREST API error: code={} message={}",
                mapped.code,
                mapped.message,
            )
            raise mapped from error

    async def ping(self) -> bool:
        """Verifica se o PostgREST responde no endpoint raiz."""
        headers = self._auth.headers() if self._auth is not None else {}
        response = await self.session.get(str(self._client.base_url), headers=headers)
        return response.is_success

    async def aclose(self) -> None:
        """Fecha o pool de conexões, caso seja o dono da sessão."""
        if self._owns_session:
            await self.session.aclose()

    async def __aenter__(self) -> "PostgrestClient":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.aclose()
