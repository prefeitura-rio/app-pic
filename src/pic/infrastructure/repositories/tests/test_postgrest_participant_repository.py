import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from src.core.security.permissions_models import UserPermissions
from src.pic.domain.errors import ForbiddenError, ValidationError
from src.pic.domain.models.filters import FilterCriteria
from src.pic.domain.models.pagination import PaginationParams, SortParams
from src.pic.infrastructure.postgrest_client.client import PostgrestClient
from src.pic.infrastructure.postgrest_client.config import PostgrestClientConfig
from src.pic.infrastructure.postgrest_client.errors import PostgrestError
from src.pic.infrastructure.repositories.helpers.filter_vocabulary import (
    PROTOCOLO_DESCRICOES,
)
from src.pic.infrastructure.repositories.helpers.participant_query_mapping import (
    PROTOCOLO_STATUS_COLUMNS,
)
from src.pic.infrastructure.repositories.postgrest_participant_repository import (
    PostgrestParticipantRepository,
)

CONFIG = PostgrestClientConfig(
    base_url="https://data-proxy.example/",
    schema="app_pequenos_cariocas",
    token_url="https://keycloak.example/token",
    client_id="pic-client",
    client_secret="pic-secret",
)

USER_TOKEN = "user-jwt-token"

SUPER_ADMIN = UserPermissions(
    cpf="11111111111", is_admin=True, is_super_admin=True, secretarias_acesso=[]
)

PARTIAL_SMS = UserPermissions(
    cpf="22222222222",
    is_admin=False,
    is_super_admin=False,
    secretarias_acesso=["SMS"],
)

PARTIAL_SMAS = UserPermissions(
    cpf="44444444444",
    is_admin=False,
    is_super_admin=False,
    secretarias_acesso=["SMAS"],
)

NO_ACCESS = UserPermissions(
    cpf="33333333333",
    is_admin=False,
    is_super_admin=False,
    secretarias_acesso=[],
)


def resumo_row(membro_id: str, bairro: str = "Centro", situacao: str = "Atenção", **overrides):
    """One `endpoint_participante_resumo` row (pre-aggregated counters)."""
    row = {
        "id_familia": f"FAM-{membro_id}",
        "id_membro_familia": membro_id,
        "nome": f"NOME {membro_id}",
        "cpf": f"{int(membro_id):011d}",
        "grupo": "Criança",
        "bairro": bairro,
        "idade": 3,
        "status": "Ativo",
        "situacao": situacao,
        "raca": "branca",
        "total_fracao": "7/7",
        "assistencia_fracao": "3/3",
        "educacao_fracao": "0/0",
        "saude_fracao": "4/4",
        "total_protocolos_irregular": 0,
        "total_protocolos_regular": 7,
        "assistencia_protocolos_total": 3,
        "assistencia_protocolos_regular": 3,
        "assistencia_protocolos_irregular": 0,
        "educacao_protocolos_total": 0,
        "educacao_protocolos_regular": 0,
        "educacao_protocolos_irregular": 0,
        "saude_protocolos_total": 4,
        "saude_protocolos_regular": 4,
        "saude_protocolos_irregular": 0,
    }
    row.update(overrides)
    return row


def protocolo_row(
    membro_id: str,
    *,
    protocolo_id: str = "sms_x",
    secretaria: str = "SMS",
    status_label: str = "Regular",
):
    return {
        "id_membro_familia": membro_id,
        "protocolo_id": protocolo_id,
        "protocolo_secretaria": secretaria,
        "protocolo_descricao": "descricao",
        "protocolo_status": "regular",
        "protocolo_irregular_indicador": False,
        "protocolo_status_label": status_label,
        "cpf_particao": 1,
    }


def produto_row(
    membro_id: str,
    *,
    secretaria: str = "SMS",
    protocolo_id: str = "sms_x",
    status_label: str = "Regular",
    **overrides,
):
    """One `endpoint_participante_protocolos` row (produto = participante x protocolo)."""
    row = {
        **resumo_row(membro_id),
        **protocolo_row(
            membro_id,
            secretaria=secretaria,
            protocolo_id=protocolo_id,
            status_label=status_label,
        ),
    }
    row.update(overrides)
    return row


def wide_row(
    membro_id: str,
    *,
    protocolos: dict[str, str | None] | None = None,
    **overrides,
):
    """One `endpoint_participante_protocolos_wide` row.

    One row per participant: the resumo columns plus one status column per
    protocol (NULL when the participant lacks the protocol).
    """
    row = {
        **resumo_row(membro_id),
        **dict.fromkeys(PROTOCOLO_STATUS_COLUMNS),
    }
    if protocolos:
        row.update(protocolos)
    row.update(overrides)
    return row


class FakeDataProxy:
    """Fakes the data-proxy PostgREST behind one MockTransport.

    Honors limit/offset and simple column filters (`eq.`, `ilike.`, `in.`,
    `is.`) over the canned rows per table, and returns a Content-Range header
    when the request carries `Prefer: count=<method>`. `or` params are
    partially emulated: only `gt`/`lt` terms (the secretaria restriction
    `or=(<prefix>_protocolos_total.gt.0,...)`) are enforced; other terms
    (e.g. free-text search) are ignored, mirroring the old fake.
    """

    def __init__(self, rows_by_table: dict[str, list[dict]]):
        self.rows_by_table = rows_by_table
        self.requests: list[httpx.Request] = []
        self.error_status: int | None = None
        self.error_body: dict | None = None
        self.error_text: str | None = None
        self.transport_error: Exception | None = None

    @staticmethod
    def _matches_or_term(row: dict, term: str) -> bool:
        """One `or` term: `column.op.operand` (eq/gt/lt/not.is.null)."""
        column, _, rest = term.partition(".")
        op, _, operand = rest.partition(".")
        if op == "not":
            return operand != "is.null" or row.get(column) is not None
        if op == "eq":
            return str(row.get(column)) == operand
        if op == "gt":
            row_value = row.get(column)
            return row_value is not None and float(row_value) > float(operand)
        if op == "lt":
            row_value = row.get(column)
            return row_value is not None and float(row_value) < float(operand)
        return False

    @staticmethod
    def _or_term_supported(term: str) -> bool:
        _, _, rest = term.partition(".")
        op, _, _ = rest.partition(".")
        return op in {"eq", "gt", "lt", "not"}

    @staticmethod
    def _matches(row: dict, params: httpx.QueryParams) -> bool:
        for key, value in params.items():
            if key in {"select", "order", "limit", "offset"}:
                continue
            if key == "or":
                # One or-group per `or` param (ANDed between params, ORed
                # inside). Unsupported terms (e.g. the free-text search
                # ilike) are ignored, mirroring the old fake.
                terms = value.strip("()").split(",")
                supported = [
                    term
                    for term in terms
                    if FakeDataProxy._or_term_supported(term)
                ]
                if supported and not any(
                    FakeDataProxy._matches_or_term(row, term)
                    for term in supported
                ):
                    return False
                continue
            if not isinstance(value, str) or "." not in value:
                continue
            op, _, operand = value.partition(".")
            if op == "not":
                # `col=not.is.null` column filter (wide protocol columns).
                if operand == "is.null" and row.get(key) is None:
                    return False
                continue
            if op not in {"eq", "ilike", "in", "is"}:
                continue
            row_value = row.get(key)
            if op == "eq":
                if str(row_value) != operand:
                    return False
            elif op == "ilike":
                pattern = (
                    operand.replace("\\_", "_")
                    .replace("\\%", "%")
                    .replace("\\\\", "\\")
                )
                if str(row_value or "").lower() != pattern.lower():
                    return False
            elif op == "in":
                allowed = [v.strip() for v in operand.strip("()").split(",")]
                if str(row_value) not in allowed:
                    return False
            elif op == "is":
                if bool(row_value) != (operand == "true"):
                    return False
        return True

    async def __call__(self, request: httpx.Request) -> httpx.Response:
        if request.url.host == "keycloak.example":
            return httpx.Response(
                200,
                json={"access_token": "client-credentials-token", "expires_in": 3600},
            )

        self.requests.append(request)
        if self.transport_error is not None:
            raise self.transport_error
        if self.error_status is not None:
            if self.error_text is not None:
                return httpx.Response(
                    self.error_status, text=self.error_text, request=request
                )
            return httpx.Response(
                self.error_status,
                json=self.error_body
                or {"message": "boom", "code": "500", "hint": None, "details": None},
                request=request,
            )

        table = request.url.path.lstrip("/")
        rows = [
            row
            for row in self.rows_by_table.get(table, [])
            if self._matches(row, request.url.params)
        ]
        params = request.url.params

        # Aggregate queries: GROUP BY (`<cols>,count()`) or pure aggregates
        # (`col:col.count()`/`col:col.max()` -> single row), like PostgREST
        # where each aggregate is aliased with its own column.
        select = params.get("select")
        if select and select != "*":
            items = list(select.split(","))
            if all(
                item.endswith(".count()") or item.endswith(".max()")
                for item in items
            ):
                single: dict[str, int | None] = {}
                for item in items:
                    head = item.removesuffix(".count()").removesuffix(".max()")
                    column = head.split(":", 1)[-1]
                    values = [row.get(column) for row in rows]
                    present = [v for v in values if v is not None]
                    if item.endswith(".count()"):
                        single[column] = len(present)
                    else:
                        single[column] = max(present) if present else None
                rows = [single]
            elif "count()" in select:
                columns = [c for c in items if c != "count()"]
                grouped: dict[tuple, int] = {}
                for row in rows:
                    key = tuple(row.get(column) for column in columns)
                    grouped[key] = grouped.get(key, 0) + 1
                rows = [
                    {**dict(zip(columns, key, strict=True)), "count": count}
                    for key, count in grouped.items()
                ]

        limit = int(params["limit"]) if "limit" in params else None
        offset = int(params["offset"]) if "offset" in params else 0
        page = rows[offset : offset + limit] if limit is not None else rows[offset:]

        headers = {}
        if "count=" in request.headers.get("prefer", ""):
            headers["Content-Range"] = f"{offset}-{len(rows)}/{len(rows)}"
        return httpx.Response(200, json=page, headers=headers, request=request)


@pytest.fixture
def make_repo():
    def _make(
        rows_by_table: dict[str, list[dict]],
        redis_client=None,
    ) -> tuple[PostgrestParticipantRepository, FakeDataProxy]:
        fake = FakeDataProxy(rows_by_table)
        client = PostgrestClient(CONFIG, transport=httpx.MockTransport(fake))
        return (
            PostgrestParticipantRepository(client, redis_client=redis_client),
            fake,
        )

    return _make


# ---------------------------------------------------------------------------
# List — super admin (full access, single wide query)
# ---------------------------------------------------------------------------


async def test_list_pushes_filters_sort_pagination_and_user_token(make_repo):
    rows = [
        resumo_row("1", bairro="Engenho da Rainha", id_cre="03"),
        resumo_row("2", bairro="Engenho da Rainha", id_cre="03"),
    ]
    repo, fake = make_repo({"endpoint_participante_protocolos_wide": rows})

    data, meta = await repo.list_participants(
        filters=FilterCriteria(status="Ativo", bairro="Engenho da Rainha", cre="03"),
        pagination=PaginationParams(page=2, page_size=50),
        sort=SortParams(sort_by="bairro", sort_order="desc"),
        permissions=SUPER_ADMIN,
        user_token=USER_TOKEN,
    )

    assert len(fake.requests) == 1
    sent = fake.requests[0]
    assert sent.headers["authorization"] == f"Bearer {USER_TOKEN}"
    assert sent.headers["accept-profile"] == "app_pequenos_cariocas"
    assert sent.url.path == "/endpoint_participante_protocolos_wide"
    params = sent.url.params
    select = params["select"]
    assert select.startswith("id_familia,id_membro_familia,nome,cpf,grupo,bairro,idade,status,raca")
    assert "situacao" in select
    assert "total_fracao" in select
    assert "total_protocolos_irregular" in select
    assert "count()" not in select  # wide: one row per participant
    assert params["status"] == "ilike.Ativo"
    assert params["bairro"] == "ilike.Engenho da Rainha"
    assert params["id_cre"] == "eq.03"
    assert params["order"] == ("bairro.desc.nullslast,id_membro_familia.asc.nullslast")
    assert params["limit"] == "50"
    assert params["offset"] == "50"
    # The wide relation is a view: exact count (estimated hallucinates).
    assert "count=exact" in sent.headers["prefer"]

    # Page 2 of a 2-row set is empty (server-side offset applies); the count
    # still reflects the full filtered set.
    assert data == []
    assert meta.page == 2
    assert meta.page_size == 50
    assert meta.total_rows == 2
    assert meta.total_pages == 1
    assert meta.cache_hit is False
    assert meta.can_view_dashboard is None
    assert meta.profiling["filters_applied"] == 3


# ---------------------------------------------------------------------------
# List — forced protocol filters (access validation)
# ---------------------------------------------------------------------------


async def test_forced_descricao_outside_access_raises_forbidden(make_repo):
    repo, fake = make_repo({"endpoint_participante_protocolos_wide": []})

    with pytest.raises(ForbiddenError):
        await repo.list_participants(
            filters=FilterCriteria(
                protocolo_descricao="sms_vacinacao_pentavalente"
            ),
            pagination=PaginationParams(),
            sort=SortParams(),
            permissions=PARTIAL_SMAS,
        )
    assert len(fake.requests) == 0


async def test_forced_descricao_unknown_id_raises_validation_error(make_repo):
    repo, fake = make_repo({"endpoint_participante_protocolos_wide": []})

    with pytest.raises(ValidationError):
        await repo.list_participants(
            filters=FilterCriteria(protocolo_descricao="protocolo_inventado"),
            pagination=PaginationParams(),
            sort=SortParams(),
            permissions=SUPER_ADMIN,
        )
    assert len(fake.requests) == 0


async def test_forced_secretaria_outside_access_raises_forbidden(make_repo):
    repo, fake = make_repo({"endpoint_participante_protocolos_wide": []})

    with pytest.raises(ForbiddenError):
        await repo.list_participants(
            filters=FilterCriteria(protocolo_secretaria="SMS"),
            pagination=PaginationParams(),
            sort=SortParams(),
            permissions=PARTIAL_SMAS,
        )
    assert len(fake.requests) == 0


async def test_forced_secretaria_unknown_value_raises_validation_error(make_repo):
    repo, fake = make_repo({"endpoint_participante_protocolos_wide": []})

    with pytest.raises(ValidationError):
        await repo.list_participants(
            filters=FilterCriteria(protocolo_secretaria="XYZ"),
            pagination=PaginationParams(),
            sort=SortParams(),
            permissions=SUPER_ADMIN,
        )
    assert len(fake.requests) == 0


async def test_own_secretaria_protocol_filters_pass_validation(make_repo):
    rows = [
        wide_row("1", protocolos={"smas_acesso_alimentacao": "Atenção"})
    ]
    repo, fake = make_repo({"endpoint_participante_protocolos_wide": rows})

    data, _ = await repo.list_participants(
        filters=FilterCriteria(
            protocolo_descricao="smas_acesso_alimentacao",
            protocolo_secretaria="SMAS",
        ),
        pagination=PaginationParams(),
        sort=SortParams(),
        permissions=PARTIAL_SMAS,
    )
    assert len(fake.requests) == 1
    assert len(data) == 1


async def test_list_multi_value_filter_uses_in(make_repo):
    repo, fake = make_repo({"endpoint_participante_protocolos_wide": []})
    await repo.list_participants(
        filters=FilterCriteria(bairro="A|B"),
        pagination=PaginationParams(page=1, page_size=20),
        sort=SortParams(),
        permissions=SUPER_ADMIN,
    )
    assert fake.requests[0].url.params["bairro"] == "in.(A,B)"


async def test_list_boolean_filter_uses_is(make_repo):
    repo, fake = make_repo({"endpoint_participante_protocolos_wide": []})
    await repo.list_participants(
        filters=FilterCriteria(has_bolsa_familia=True),
        pagination=PaginationParams(page=1, page_size=20),
        sort=SortParams(),
        permissions=SUPER_ADMIN,
    )
    assert fake.requests[0].url.params["has_bolsa_familia"] == "is.true"


async def test_list_search_uses_ilike_or_over_four_columns(make_repo):
    repo, fake = make_repo({"endpoint_participante_protocolos_wide": []})
    await repo.list_participants(
        filters=FilterCriteria(search="maria"),
        pagination=PaginationParams(page=1, page_size=20),
        sort=SortParams(),
        permissions=SUPER_ADMIN,
    )
    or_param = fake.requests[0].url.params["or"]
    assert or_param == (
        "(nome.ilike.%maria%,cpf.ilike.%maria%,"
        "id_membro_familia.ilike.%maria%,id_familia.ilike.%maria%)"
    )


async def test_list_page_size_minus_one_loops_pages_without_server_pagination(
    make_repo,
):
    rows = [resumo_row(str(i)) for i in range(1500)]
    repo, fake = make_repo({"endpoint_participante_protocolos_wide": rows})

    data, meta = await repo.list_participants(
        filters=FilterCriteria(),
        pagination=PaginationParams(page=1, page_size=-1),
        sort=SortParams(),
        permissions=SUPER_ADMIN,
    )

    assert len(data) == 1500
    assert meta.page_size is None
    assert meta.total_pages == 1
    assert meta.total_rows == 1500
    assert len(fake.requests) == 2
    assert fake.requests[0].url.params["limit"] == "1000"
    assert fake.requests[0].url.params["offset"] == "0"
    assert fake.requests[1].url.params["offset"] == "1000"


async def test_list_sorts_by_default_column_when_sort_not_requested(make_repo):
    repo, fake = make_repo({"endpoint_participante_protocolos_wide": []})
    await repo.list_participants(
        filters=FilterCriteria(),
        pagination=PaginationParams(page=1, page_size=20),
        sort=SortParams(),
        permissions=SUPER_ADMIN,
    )
    assert fake.requests[0].url.params["order"].startswith("nome.asc")


async def test_list_situacao_filter_is_pushed_for_full_access(make_repo):
    rows = [
        resumo_row("1", situacao="Atenção"),
        resumo_row("2", situacao="Regular"),
    ]
    repo, fake = make_repo({"endpoint_participante_protocolos_wide": rows})

    await repo.list_participants(
        filters=FilterCriteria(situacao="ATENÇÃO"),
        pagination=PaginationParams(page=1, page_size=20),
        sort=SortParams(),
        permissions=SUPER_ADMIN,
    )

    assert fake.requests[0].url.params["situacao"] == "ilike.ATENÇÃO"
    assert fake.requests[0].url.params["limit"] == "20"


async def test_list_sort_by_total_uses_irregularidade_column(make_repo):
    repo, fake = make_repo({"endpoint_participante_protocolos_wide": []})
    await repo.list_participants(
        filters=FilterCriteria(),
        pagination=PaginationParams(page=1, page_size=20),
        sort=SortParams(sort_by="total_fracao", sort_order="asc"),
        permissions=SUPER_ADMIN,
    )
    assert fake.requests[0].url.params["order"].startswith(
        "total_protocolos_irregular.asc"
    )


# ---------------------------------------------------------------------------
# List — partial access (single wide query + in-app per-secretaria view)
# ---------------------------------------------------------------------------


async def test_list_partial_secretaria_computes_view_and_drops_invisible_rows(
    make_repo,
):
    rows = [
        resumo_row(
            "1",
            saude_protocolos_total=1,
            saude_protocolos_regular=1,
            saude_protocolos_irregular=0,
            saude_fracao="1/1",
        ),
        resumo_row("2", saude_protocolos_total=0),
    ]
    repo, fake = make_repo({"endpoint_participante_protocolos_wide": rows})

    data, meta = await repo.list_participants(
        filters=FilterCriteria(),
        pagination=PaginationParams(page=1, page_size=20),
        sort=SortParams(),
        permissions=PARTIAL_SMS,
        user_token=USER_TOKEN,
    )

    # Single wide request: secretaria restriction via or on the pre-
    # aggregated counters, pushdown pagination, exact count.
    assert len(fake.requests) == 1
    req = fake.requests[0]
    assert req.headers["authorization"] == f"Bearer {USER_TOKEN}"
    assert req.url.path == "/endpoint_participante_protocolos_wide"
    assert req.url.params["or"] == "(saude_protocolos_total.gt.0)"
    assert "protocolo_secretaria" not in req.url.params
    assert req.url.params["limit"] == "20"
    assert "count=exact" in req.headers["prefer"]

    # Only row "1" has SMS protocols; row "2" is dropped by the restriction.
    assert [item.id_membro_familia for item in data] == ["1"]
    item = data[0]
    assert item.total_protocolos_irregular == 0
    assert item.total_fracao == "1/1"
    assert item.saude_fracao == "1/1"
    assert item.assistencia_fracao is None
    assert item.educacao_fracao is None
    assert item.situacao is None
    assert item.status == "Ativo"
    assert meta.total_rows == 1


async def test_list_partial_select_only_allowed_secretaria_columns(make_repo):
    repo, fake = make_repo({"endpoint_participante_protocolos_wide": []})
    await repo.list_participants(
        filters=FilterCriteria(),
        pagination=PaginationParams(page=1, page_size=20),
        sort=SortParams(),
        permissions=PARTIAL_SMS,
    )
    select = fake.requests[0].url.params["select"]
    assert "saude_fracao" in select
    assert "saude_protocolos_total" in select
    assert "assistencia_fracao" not in select
    assert "educacao_fracao" not in select
    assert "situacao" not in select
    assert "status" in select
    assert "count()" not in select


async def test_list_partial_ignores_situacao_filter(make_repo):
    repo, fake = make_repo({"endpoint_participante_protocolos_wide": [resumo_row("1")]})
    await repo.list_participants(
        filters=FilterCriteria(situacao="ATENÇÃO"),
        pagination=PaginationParams(page=1, page_size=20),
        sort=SortParams(),
        permissions=PARTIAL_SMS,
    )
    assert "situacao" not in fake.requests[0].url.params


async def test_list_partial_sort_by_situacao_falls_back_to_nome(make_repo):
    repo, fake = make_repo({"endpoint_participante_protocolos_wide": [resumo_row("1")]})
    await repo.list_participants(
        filters=FilterCriteria(),
        pagination=PaginationParams(page=1, page_size=20),
        sort=SortParams(sort_by="situacao", sort_order="asc"),
        permissions=PARTIAL_SMS,
    )
    assert fake.requests[0].url.params["order"].startswith("nome.asc")


async def test_list_partial_sort_by_total_uses_secretaria_irregularidade(make_repo):
    repo, fake = make_repo({"endpoint_participante_protocolos_wide": [resumo_row("1")]})
    await repo.list_participants(
        filters=FilterCriteria(),
        pagination=PaginationParams(page=1, page_size=20),
        sort=SortParams(sort_by="total_fracao", sort_order="asc"),
        permissions=PARTIAL_SMS,
    )
    assert fake.requests[0].url.params["order"].startswith(
        "saude_protocolos_irregular.asc"
    )


async def test_list_partial_sort_by_total_with_two_secretarias_uses_global(make_repo):
    permissions = UserPermissions(
        cpf="44444444444",
        is_admin=False,
        is_super_admin=False,
        secretarias_acesso=["SMS", "SMAS"],
    )
    repo, fake = make_repo({"endpoint_participante_protocolos_wide": [resumo_row("1")]})
    await repo.list_participants(
        filters=FilterCriteria(),
        pagination=PaginationParams(page=1, page_size=20),
        sort=SortParams(sort_by="total_fracao", sort_order="asc"),
        permissions=permissions,
    )
    assert fake.requests[0].url.params["order"].startswith(
        "total_protocolos_irregular.asc"
    )


async def test_list_no_access_keeps_rows_with_null_protocol_fields(make_repo):
    repo, _ = make_repo({"endpoint_participante_protocolos_wide": [resumo_row("1")]})
    data, meta = await repo.list_participants(
        filters=FilterCriteria(),
        pagination=PaginationParams(page=1, page_size=20),
        sort=SortParams(),
        permissions=NO_ACCESS,
    )
    assert meta.total_rows == 1
    item = data[0]
    assert item.status == "Ativo"
    assert item.total_fracao is None
    assert item.total_protocolos_irregular is None
    assert item.saude_fracao is None
    assert item.situacao is None


# ---------------------------------------------------------------------------
# Protocolo filters (wide table: one row per participant, one column per
# protocol)
# ---------------------------------------------------------------------------


async def test_list_protocolo_secretaria_filter_uses_wide_counters(make_repo):
    repo, fake = make_repo(
        {
            "endpoint_participante_protocolos_wide": [
                wide_row(
                    "1",
                    saude_protocolos_total=1,
                    educacao_protocolos_total=0,
                    assistencia_protocolos_total=0,
                ),
                wide_row(
                    "2",
                    saude_protocolos_total=0,
                    educacao_protocolos_total=1,
                    assistencia_protocolos_total=0,
                ),
            ]
        }
    )

    data, meta = await repo.list_participants(
        filters=FilterCriteria(protocolo_secretaria="SMS"),
        pagination=PaginationParams(page=1, page_size=20),
        sort=SortParams(),
        permissions=SUPER_ADMIN,
    )

    assert len(fake.requests) == 1
    wide_req = fake.requests[0]
    assert wide_req.url.path == "/endpoint_participante_protocolos_wide"
    assert "count()" not in wide_req.url.params["select"]
    assert wide_req.url.params["or"] == "(saude_protocolos_total.gt.0)"
    assert "protocolo_secretaria" not in wide_req.url.params
    # The wide relation is a view: exact count (estimated hallucinates over
    # views without relation statistics).
    assert "count=exact" in wide_req.headers["prefer"]
    assert "count=estimated" not in wide_req.headers["prefer"]

    # One row per participant: the Content-Range count equals people.
    assert [item.id_membro_familia for item in data] == ["1"]
    assert meta.total_rows == 1


async def test_list_protocolo_multi_secretaria_union(make_repo):
    repo, fake = make_repo(
        {
            "endpoint_participante_protocolos_wide": [
                wide_row(
                    "1",
                    saude_protocolos_total=1,
                    educacao_protocolos_total=0,
                    assistencia_protocolos_total=0,
                ),
                wide_row(
                    "2",
                    saude_protocolos_total=0,
                    educacao_protocolos_total=1,
                    assistencia_protocolos_total=0,
                ),
                wide_row(
                    "3",
                    saude_protocolos_total=0,
                    educacao_protocolos_total=0,
                    assistencia_protocolos_total=0,
                ),
            ]
        }
    )

    data, meta = await repo.list_participants(
        filters=FilterCriteria(protocolo_secretaria="SMS|SME"),
        pagination=PaginationParams(page=1, page_size=20),
        sort=SortParams(),
        permissions=SUPER_ADMIN,
    )

    assert fake.requests[0].url.params["or"] == (
        "(saude_protocolos_total.gt.0,educacao_protocolos_total.gt.0)"
    )
    assert [item.id_membro_familia for item in data] == ["1", "2"]
    assert meta.total_rows == 2


async def test_list_protocolo_descricao_is_not_null_on_wide_column(make_repo):
    repo, fake = make_repo(
        {
            "endpoint_participante_protocolos_wide": [
                wide_row("1", protocolos={"sms_vacinacao_pentavalente": "Regular"}),
                wide_row("2"),
            ]
        }
    )

    data, meta = await repo.list_participants(
        filters=FilterCriteria(protocolo_descricao="sms_vacinacao_pentavalente"),
        pagination=PaginationParams(page=1, page_size=20),
        sort=SortParams(),
        permissions=SUPER_ADMIN,
    )

    assert len(fake.requests) == 1
    wide_req = fake.requests[0]
    assert wide_req.url.path == "/endpoint_participante_protocolos_wide"
    assert wide_req.url.params["sms_vacinacao_pentavalente"] == "not.is.null"
    assert [item.id_membro_familia for item in data] == ["1"]
    assert meta.total_rows == 1


async def test_list_protocolo_multi_descricao_requires_all_protocols(make_repo):
    """Multi-select descricao = intersection (AND) — regression for the
    count bug: a participant matching two selected protocols counts once."""
    repo, fake = make_repo(
        {
            "endpoint_participante_protocolos_wide": [
                wide_row(
                    "1",
                    protocolos={
                        "sms_vacinacao_pentavalente": "Regular",
                        "sme_frequencia_escolar": "Regular",
                    },
                ),
                wide_row(
                    "2",
                    protocolos={"sms_vacinacao_pentavalente": "Regular"},
                ),
            ]
        }
    )

    data, meta = await repo.list_participants(
        filters=FilterCriteria(
            protocolo_descricao="sms_vacinacao_pentavalente|sme_frequencia_escolar"
        ),
        pagination=PaginationParams(page=1, page_size=20),
        sort=SortParams(),
        permissions=SUPER_ADMIN,
    )

    assert len(fake.requests) == 1
    params = fake.requests[0].url.params
    assert params["sms_vacinacao_pentavalente"] == "not.is.null"
    assert params["sme_frequencia_escolar"] == "not.is.null"
    assert "count=exact" in fake.requests[0].headers["prefer"]
    assert [item.id_membro_familia for item in data] == ["1"]
    assert meta.total_rows == 1


async def test_list_protocolo_status_matches_any_protocol_column(make_repo):
    repo, fake = make_repo(
        {
            "endpoint_participante_protocolos_wide": [
                wide_row("1", protocolos={"sms_vacinacao_pentavalente": "Atenção"}),
                wide_row("2", protocolos={"sme_frequencia_escolar": "Regular"}),
                wide_row("3"),
            ]
        }
    )

    data, meta = await repo.list_participants(
        filters=FilterCriteria(protocolo_status="Atenção"),
        pagination=PaginationParams(page=1, page_size=20),
        sort=SortParams(),
        permissions=SUPER_ADMIN,
    )

    or_param = fake.requests[0].url.params["or"]
    assert or_param.startswith("(") and or_param.endswith(")")
    terms = or_param.strip("()").split(",")
    assert len(terms) == len(PROTOCOLO_STATUS_COLUMNS)
    assert all(term.endswith(".eq.Atenção") for term in terms)
    assert [item.id_membro_familia for item in data] == ["1"]
    assert meta.total_rows == 1


async def test_list_protocolo_descricao_and_status_requires_status_per_protocol(
    make_repo,
):
    repo, fake = make_repo(
        {
            "endpoint_participante_protocolos_wide": [
                wide_row(
                    "1",
                    protocolos={
                        "sms_vacinacao_pentavalente": "Regular",
                        "sme_frequencia_escolar": "Regular",
                    },
                ),
                wide_row(
                    "2",
                    protocolos={
                        "sms_vacinacao_pentavalente": "Regular",
                        "sme_frequencia_escolar": "Atenção",
                    },
                ),
                wide_row("3"),
            ]
        }
    )

    data, meta = await repo.list_participants(
        filters=FilterCriteria(
            protocolo_descricao="sms_vacinacao_pentavalente|sme_frequencia_escolar",
            protocolo_status="Regular",
        ),
        pagination=PaginationParams(page=1, page_size=20),
        sort=SortParams(),
        permissions=SUPER_ADMIN,
    )

    params = fake.requests[0].url.params
    assert params["sms_vacinacao_pentavalente"] == "eq.Regular"
    assert params["sme_frequencia_escolar"] == "eq.Regular"
    assert [item.id_membro_familia for item in data] == ["1"]
    assert meta.total_rows == 1


async def test_list_protocolo_descricao_and_multi_status_uses_in_per_protocol(
    make_repo,
):
    repo, fake = make_repo(
        {
            "endpoint_participante_protocolos_wide": [
                wide_row(
                    "1",
                    protocolos={
                        "sms_vacinacao_pentavalente": "Regular",
                        "sme_frequencia_escolar": "Atenção",
                    },
                ),
            ]
        }
    )

    await repo.list_participants(
        filters=FilterCriteria(
            protocolo_descricao="sms_vacinacao_pentavalente|sme_frequencia_escolar",
            protocolo_status="Regular|Atenção",
        ),
        pagination=PaginationParams(page=1, page_size=20),
        sort=SortParams(),
        permissions=SUPER_ADMIN,
    )

    params = fake.requests[0].url.params
    assert params["sms_vacinacao_pentavalente"] == "in.(Regular,Atenção)"
    assert params["sme_frequencia_escolar"] == "in.(Regular,Atenção)"


async def test_list_protocolo_filter_pages_have_single_offset_and_limit(make_repo):
    wide_rows = [wide_row(str(i), saude_protocolos_total=1) for i in range(1500)]
    repo, fake = make_repo(
        {"endpoint_participante_protocolos_wide": wide_rows}
    )

    data, _ = await repo.list_participants(
        filters=FilterCriteria(protocolo_secretaria="SMS"),
        pagination=PaginationParams(page=1, page_size=-1),
        sort=SortParams(),
        permissions=SUPER_ADMIN,
    )

    # Download mode loops the pages. Each page must carry exactly one
    # offset/limit pair (regression: the mutable postgrest-py builders used
    # to accumulate params page after page).
    assert len(fake.requests) == 2
    for index, expected_offset in enumerate(["0", "1000"]):
        params = fake.requests[index].url.params
        assert params.get_list("offset") == [expected_offset]
        assert params.get_list("limit") == ["1000"]

    assert len(data) == 1500


async def test_list_protocolo_filter_restricts_to_allowed_secretaria_for_partial(
    make_repo,
):
    repo, fake = make_repo(
        {
            "endpoint_participante_protocolos_wide": [
                wide_row(
                    "1",
                    saude_protocolos_total=1,
                    educacao_protocolos_total=1,
                    protocolos={
                        "sms_vacinacao_pentavalente": "Regular",
                        "sme_frequencia_escolar": "Regular",
                    },
                ),
            ]
        }
    )

    await repo.list_participants(
        filters=FilterCriteria(protocolo_descricao="sms_vacinacao_pentavalente"),
        pagination=PaginationParams(page=1, page_size=20),
        sort=SortParams(),
        permissions=PARTIAL_SMS,
    )

    # Single request: protocol filter AND the accessible-secretaria
    # restriction (`or` group) chained on the wide table.
    assert len(fake.requests) == 1
    wide_req = fake.requests[0]
    assert wide_req.url.path == "/endpoint_participante_protocolos_wide"
    assert wide_req.url.params["sms_vacinacao_pentavalente"] == "not.is.null"
    assert wide_req.url.params["or"] == "(saude_protocolos_total.gt.0)"


async def test_list_protocolo_filter_with_no_matches_returns_empty(make_repo):
    repo, fake = make_repo(
        {
            "endpoint_participante_protocolos_wide": [
                wide_row(
                    "1",
                    saude_protocolos_total=0,
                    educacao_protocolos_total=1,
                    assistencia_protocolos_total=0,
                ),
            ]
        }
    )

    data, meta = await repo.list_participants(
        filters=FilterCriteria(protocolo_secretaria="SMS"),
        pagination=PaginationParams(page=1, page_size=20),
        sort=SortParams(),
        permissions=SUPER_ADMIN,
    )

    assert data == []
    assert meta.total_rows == 0
    assert meta.total_pages == 0
    assert len(fake.requests) == 1  # only the wide query


async def test_list_protocolo_filter_with_no_secretaria_access_is_forbidden(
    make_repo,
):
    repo, fake = make_repo(
        {"endpoint_participante_protocolos_wide": [wide_row("1")]}
    )

    with pytest.raises(ForbiddenError):
        await repo.list_participants(
            filters=FilterCriteria(protocolo_secretaria="SMS"),
            pagination=PaginationParams(page=1, page_size=20),
            sort=SortParams(),
            permissions=NO_ACCESS,
        )
    assert len(fake.requests) == 0


# ---------------------------------------------------------------------------
# Cache (per-user, TTL 1800, skipped in download mode)
# ---------------------------------------------------------------------------


class TestRepositoryCache:
    def _make_redis(self, cached_payload: dict | None = None):
        redis = MagicMock()
        if cached_payload is None:
            redis.get = AsyncMock(return_value=None)
        else:
            redis.get = AsyncMock(
                return_value=json.dumps(cached_payload).encode()
            )
        redis.set = AsyncMock()
        return redis

    @pytest.mark.asyncio
    async def test_cache_miss_writes_to_redis(self, make_repo):
        redis = self._make_redis(None)
        repo, _ = make_repo({"endpoint_participante_protocolos_wide": [resumo_row("1")]}, redis_client=redis)
        await repo.list_participants(
            filters=FilterCriteria(),
            pagination=PaginationParams(page=1, page_size=20),
            sort=SortParams(),
            permissions=SUPER_ADMIN,
        )
        redis.set.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_cache_hit_skips_fetches(self, make_repo):
        payload = {
            "data": [],
            "meta": {
                "page": 1,
                "page_size": 20,
                "total_rows": 0,
                "total_pages": 0,
                "cache_hit": False,
                "profiling": None,
                "can_view_dashboard": None,
            },
        }
        redis = self._make_redis(payload)
        repo, fake = make_repo({"endpoint_participante_protocolos_wide": []}, redis_client=redis)
        data, meta = await repo.list_participants(
            filters=FilterCriteria(),
            pagination=PaginationParams(page=1, page_size=20),
            sort=SortParams(),
            permissions=SUPER_ADMIN,
        )
        assert len(fake.requests) == 0
        assert data == []
        assert meta.cache_hit is True

    @pytest.mark.asyncio
    async def test_bypass_cache_still_fetches_and_writes(self, make_repo):
        redis = self._make_redis(None)
        repo, fake = make_repo({"endpoint_participante_protocolos_wide": [resumo_row("1")]}, redis_client=redis)
        await repo.list_participants(
            filters=FilterCriteria(),
            pagination=PaginationParams(page=1, page_size=20),
            sort=SortParams(),
            permissions=SUPER_ADMIN,
            bypass_cache=True,
        )
        assert len(fake.requests) == 1
        redis.set.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_download_mode_skips_cache(self, make_repo):
        redis = self._make_redis(None)
        repo, _ = make_repo({"endpoint_participante_protocolos_wide": [resumo_row("1")]}, redis_client=redis)
        await repo.list_participants(
            filters=FilterCriteria(),
            pagination=PaginationParams(page=1, page_size=-1),
            sort=SortParams(),
            permissions=SUPER_ADMIN,
        )
        redis.get.assert_not_awaited()
        redis.set.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_cache_key_isolates_users(self, make_repo):
        redis = MagicMock()
        redis.get = AsyncMock(return_value=None)
        redis.set = AsyncMock()
        repo, _ = make_repo({"endpoint_participante_protocolos_wide": []}, redis_client=redis)

        await repo.list_participants(
            filters=FilterCriteria(),
            pagination=PaginationParams(page=1, page_size=20),
            sort=SortParams(),
            permissions=SUPER_ADMIN,
        )
        await repo.list_participants(
            filters=FilterCriteria(),
            pagination=PaginationParams(page=1, page_size=20),
            sort=SortParams(),
            permissions=PARTIAL_SMS,
        )

        keys = [call.args[0] for call in redis.set.await_args_list]
        assert len(keys) == 2
        assert keys[0] != keys[1]
        assert keys[0].startswith("participants_v2:")


# ---------------------------------------------------------------------------
# Detail (wide + _protocolos_detalhe + protocolo_detalhes)
# ---------------------------------------------------------------------------


def resumo_detail_row(membro_id: str = "00325420412", **overrides):
    """One full-fidelity wide-table row (resumo columns + protocol columns).

    Pre-aggregated counters are intentionally wrong (9) so tests prove the
    detail view recomputes them from the protocol rows.
    """
    row = {
        "id_familia": "02159929700",
        "id_membro_familia": membro_id,
        "nome": "ANA JULIA DE SOUZA DA SILVA",
        "cpf": "23131727756",
        "grupo": "Criança",
        "idade": 3,
        "raca": "branca",
        "nascimento_data": "2022-09-22",
        "endereco": "RUA  MOREIA 6",
        "complemento": None,
        "bairro": "Engenho da Rainha",
        "endereco_sms": {
            "endereco": "RUA PRACA",
            "complemento": None,
            "bairro": "ENGENHO DA RAINHA",
        },
        "telefone_1_ddd": "21",
        "telefone_1_numero": "968267587",
        "cohort": "2025-09-01",
        "status": "Ativo",
        "situacao": "Regular",
        "latitude": -22.867801,
        "longitude": -43.2931916,
        "total_protocolos": 9,
        "total_protocolos_irregular": 9,
        "total_protocolos_atencao": 9,
        "total_protocolos_regular": 9,
        "total_fracao": "0/9",
        "assistencia_fracao": "0/9",
        "educacao_fracao": "0/9",
        "saude_fracao": "0/9",
        "assistencia_protocolos_total": 9,
        "educacao_protocolos_total": 9,
        "saude_protocolos_total": 9,
    }
    row.update(overrides)
    return row


def detail_protocolo_row(
    membro_id: str,
    protocolo_id: str,
    secretaria: str,
    *,
    irregular: bool = False,
    status_label: str = "Regular",
):
    return {
        "id_membro_familia": membro_id,
        "protocolo_id": protocolo_id,
        "protocolo_secretaria": secretaria,
        "protocolo_descricao": "descricao",
        "protocolo_status": "atencao" if irregular else "regular",
        "protocolo_irregular_indicador": irregular,
        "protocolo_status_label": status_label,
        "cpf_particao": 1,
    }


async def test_get_participant_by_id_maps_resumo_and_protocolos_and_attaches_motivos(
    make_repo,
):
    protocolos = [
        detail_protocolo_row(
            "00325420412", "sms_visitas_domiciliares_infantil", "SMS"
        ),
        detail_protocolo_row(
            "00325420412",
            "smas_acesso_alimentacao",
            "SMAS",
            irregular=True,
            status_label="Atenção",
        ),
    ]
    motivos = [
        {
            "id_membro_familia": "00325420412",
            "protocolo_id": "smas_acesso_alimentacao",
            "protocolo_motivo": '{"motivos": ["falta de dados"], "detalhes": {}}',
        }
    ]
    repo, fake = make_repo(
        {
            "endpoint_participante_protocolos_wide": [resumo_detail_row()],
            "endpoint_participante_protocolos_detalhe": protocolos,
            "protocolo_detalhes": motivos,
        }
    )

    participante = await repo.get_participant_by_id(
        "00325420412", permissions=SUPER_ADMIN, user_token=USER_TOKEN
    )

    assert participante is not None
    assert participante.id_membro_familia == "00325420412"
    assert participante.nascimento_data.isoformat() == "2022-09-22"
    assert participante.endereco_sms.bairro == "ENGENHO DA RAINHA"
    assert participante.latitude == -22.867801
    # Counters recomputed from the protocol rows, not the resumo aggregates.
    assert participante.total_protocolos == 2
    assert participante.total_protocolos_irregular == 1
    assert participante.total_protocolos_atencao == 1
    assert participante.total_protocolos_regular == 1
    assert participante.situacao == "Atenção"
    assert participante.total_fracao == "1/2"
    assert [p.id for p in participante.protocolo_listagem] == [
        "sms_visitas_domiciliares_infantil",
        "smas_acesso_alimentacao",
    ]

    irregular = [p for p in participante.protocolo_listagem if p.irregular_indicador]
    assert len(irregular) == 1
    assert irregular[0].protocolo_motivo.motivos == ["falta de dados"]

    resumo_req = fake.requests[0]
    assert resumo_req.url.path == "/endpoint_participante_protocolos_wide"
    assert resumo_req.url.params["id_membro_familia"] == "eq.00325420412"
    assert resumo_req.headers["authorization"] == f"Bearer {USER_TOKEN}"
    protocolos_req = fake.requests[1]
    assert protocolos_req.url.path == "/endpoint_participante_protocolos_detalhe"
    assert protocolos_req.url.params["id_membro_familia"] == "eq.00325420412"
    assert "protocolo_secretaria" not in protocolos_req.url.params
    motivos_req = fake.requests[2]
    assert motivos_req.url.path == "/protocolo_detalhes"
    assert motivos_req.url.params["id_membro_familia"] == "eq.00325420412"


async def test_get_participant_by_id_returns_none_when_missing(make_repo):
    repo, _ = make_repo({"endpoint_participante_protocolos_wide": []})
    result = await repo.get_participant_by_id("nope", permissions=SUPER_ADMIN)
    assert result is None


async def test_get_participant_by_id_partial_secretaria_filters_and_recalculates(
    make_repo,
):
    protocolos = [
        detail_protocolo_row(
            "00325420412", "sms_visitas_domiciliares_infantil", "SMS"
        ),
        detail_protocolo_row(
            "00325420412",
            "smas_acesso_alimentacao",
            "SMAS",
            irregular=True,
            status_label="Atenção",
        ),
    ]
    repo, fake = make_repo(
        {
            "endpoint_participante_protocolos_wide": [resumo_detail_row()],
            "endpoint_participante_protocolos_detalhe": protocolos,
        }
    )

    result = await repo.get_participant_by_id(
        "00325420412", permissions=PARTIAL_SMS, user_token=USER_TOKEN
    )

    assert result is not None
    assert [p.id for p in result.protocolo_listagem] == [
        "sms_visitas_domiciliares_infantil"
    ]
    assert result.total_protocolos == 1
    assert result.total_protocolos_irregular == 0
    assert result.situacao == "Regular"
    assert result.total_fracao == "1/1"
    assert result.saude_protocolos_total == 1
    assert result.saude_fracao == "1/1"
    assert result.assistencia_protocolos_total is None
    assert result.assistencia_fracao is None

    protocolos_req = fake.requests[1]
    assert protocolos_req.url.path == "/endpoint_participante_protocolos_detalhe"
    assert protocolos_req.url.params["protocolo_secretaria"] == "in.(SMS)"
    # No irregular protocols left -> no motives query.
    assert [r.url.path for r in fake.requests[2:]] == []


async def test_get_participant_by_id_partial_secretaria_drops_invisible_row(make_repo):
    repo, fake = make_repo(
        {
            "endpoint_participante_protocolos_wide": [resumo_detail_row()],
            "endpoint_participante_protocolos_detalhe": [
                detail_protocolo_row("00325420412", "sme_x", "SME")
            ],
        }
    )
    result = await repo.get_participant_by_id(
        "00325420412", permissions=PARTIAL_SMS, user_token=USER_TOKEN
    )
    assert result is None
    assert [r.url.path for r in fake.requests] == [
        "/endpoint_participante_protocolos_wide",
        "/endpoint_participante_protocolos_detalhe",
    ]


async def test_get_participant_by_id_no_access_keeps_row_with_null_protocols(make_repo):
    repo, fake = make_repo({"endpoint_participante_protocolos_wide": [resumo_detail_row()]})

    result = await repo.get_participant_by_id(
        "00325420412", permissions=NO_ACCESS, user_token=USER_TOKEN
    )

    assert result is not None
    assert result.id_membro_familia == "00325420412"
    assert result.protocolo_listagem == []
    assert result.total_protocolos is None
    assert result.total_protocolos_irregular is None
    assert result.situacao is None
    assert result.total_fracao is None
    # Protocols query is skipped entirely for no-access users.
    assert [r.url.path for r in fake.requests] == ["/endpoint_participante_protocolos_wide"]


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


async def test_api_error_is_wrapped_in_postgrest_error(make_repo):
    repo, fake = make_repo({"endpoint_participante_protocolos_wide": []})
    fake.error_status = 400
    fake.error_body = {
        "message": 'column "bairro" does not exist',
        "code": "42703",
        "details": None,
        "hint": "Perhaps you meant the column bairro.",
    }

    with pytest.raises(PostgrestError) as exc_info:
        await repo.list_participants(
            filters=FilterCriteria(bairro="x"),
            pagination=PaginationParams(page=1, page_size=20),
            sort=SortParams(),
            permissions=SUPER_ADMIN,
        )
    error = exc_info.value
    assert error.message == 'column "bairro" does not exist'
    assert error.code == "42703"
    assert error.hint == "Perhaps you meant the column bairro."


async def test_transport_error_is_wrapped_in_postgrest_error(make_repo):
    repo, fake = make_repo({"endpoint_participante_protocolos_wide": []})
    fake.transport_error = httpx.ConnectError("connection refused", request=None)

    with pytest.raises(PostgrestError) as exc_info:
        await repo.list_participants(
            filters=FilterCriteria(),
            pagination=PaginationParams(page=1, page_size=20),
            sort=SortParams(),
            permissions=SUPER_ADMIN,
        )
    assert "Falha de comunicação com o data-proxy" in str(exc_info.value)


async def test_api_error_with_plain_text_body_promotes_details_to_message(make_repo):
    repo, fake = make_repo({"endpoint_participante_protocolos_wide": []})
    fake.error_status = 401
    fake.error_text = (
        "Jwt is not in the form of Header.Payload.Signature with two dots "
        "and 3 sections"
    )

    with pytest.raises(PostgrestError) as exc_info:
        await repo.list_participants(
            filters=FilterCriteria(),
            pagination=PaginationParams(page=1, page_size=20),
            sort=SortParams(),
            permissions=SUPER_ADMIN,
        )
    error = exc_info.value
    assert (
        error.message
        == "Jwt is not in the form of Header.Payload.Signature with two dots and 3 sections"
    )
    assert error.code == 401


def test_postgrest_error_from_api_error_promotes_details_when_message_is_generic():
    from postgrest.exceptions import APIError

    error = PostgrestError.from_api_error(
        APIError(
            {
                "message": "JSON could not be generated",
                "code": "403",
                "hint": None,
                "details": "b'permission denied for table endpoint_participante_resumo'",
            }
        )
    )
    assert error.message == "permission denied for table endpoint_participante_resumo"
    assert error.code == "403"
    assert (
        error.details == "b'permission denied for table endpoint_participante_resumo'"
    )


def test_postgrest_error_from_api_error_keeps_structured_message():
    from postgrest.exceptions import APIError

    error = PostgrestError.from_api_error(
        APIError(
            {
                "message": 'column "bairro" does not exist',
                "code": "42703",
                "hint": "Perhaps you meant the column bairro.",
                "details": None,
            }
        )
    )
    assert error.message == 'column "bairro" does not exist'
    assert error.code == "42703"


# ---------------------------------------------------------------------------
# Filter options (endpoint_participante_protocolos_wide aggregates)
# ---------------------------------------------------------------------------


def filtro_row(
    membro_id: str,
    *,
    bairro: str = "Centro",
    subprefeitura: str = "Centro",
    regiao_administrativa: str = "II",
    grupo: str = "Criança",
    cohort: str = "2025-09-01",
    status: str = "Ativo",
    situacao: str = "Regular",
    raca: str = "branca",
    id_cras: str = "1",
    nome_cras: str = "CRAS Centro",
    id_cre: str = "01",
    nome_cre: str = "1ª CRE",
    id_ap: str = "1.0",
    nome_ap: str = "AP 1.0",
    id_cas: str = "11",
    nome_cas: str = "CAS X",
    id_escola: str = "0101",
    nome_escola: str = "Escola A",
    id_clinica_familia: str = "010101",
    nome_clinica_familia: str = "Clinica A",
    id_equipe_familia: str = "01010101",
    nome_equipe_familia: str = "Equipe A",
    has_bolsa_familia: bool = True,
    saude_protocolos_total: int = 1,
    assistencia_protocolos_total: int = 0,
    educacao_protocolos_total: int = 0,
    **overrides,
):
    """One `endpoint_participante_protocolos_wide` row with filter columns."""
    row = {
        **wide_row(membro_id, bairro=bairro),
        "subprefeitura": subprefeitura,
        "regiao_administrativa": regiao_administrativa,
        "grupo": grupo,
        "cohort": cohort,
        "status": status,
        "situacao": situacao,
        "raca": raca,
        "id_cras": id_cras,
        "nome_cras": nome_cras,
        "id_cre": id_cre,
        "nome_cre": nome_cre,
        "id_ap": id_ap,
        "nome_ap": nome_ap,
        "id_cas": id_cas,
        "nome_cas": nome_cas,
        "id_escola": id_escola,
        "nome_escola": nome_escola,
        "id_clinica_familia": id_clinica_familia,
        "nome_clinica_familia": nome_clinica_familia,
        "id_equipe_familia": id_equipe_familia,
        "nome_equipe_familia": nome_equipe_familia,
        "has_bolsa_familia": has_bolsa_familia,
        "saude_protocolos_total": saude_protocolos_total,
        "assistencia_protocolos_total": assistencia_protocolos_total,
        "educacao_protocolos_total": educacao_protocolos_total,
    }
    row.update(overrides)
    return row


def filtro_rows() -> list[dict]:
    return [
        filtro_row(
            "1",
            bairro="Centro",
            sms_vacinacao_pentavalente="Regular",
            saude_protocolos_total=2,
        ),
        filtro_row(
            "2",
            bairro="Centro",
            sme_frequencia_escolar="Regular",
            educacao_protocolos_total=1,
            saude_protocolos_total=0,
        ),
        filtro_row(
            "3",
            bairro="Centro",
            smas_acesso_alimentacao="Atenção",
            assistencia_protocolos_total=1,
            saude_protocolos_total=0,
        ),
        filtro_row("4", bairro="Bangu", has_bolsa_familia=False),
    ]


class TestFilterOptions:
    WIDE = "endpoint_participante_protocolos_wide"

    @staticmethod
    def make_rows() -> dict[str, list[dict]]:
        return {
            TestFilterOptions.WIDE: filtro_rows(),
        }

    @pytest.mark.asyncio
    async def test_super_admin_single_aggregate_query_per_field(self, make_repo):
        repo, fake = make_repo(self.make_rows())
        options = await repo.get_filter_options(
            field="cras",
            filters=FilterCriteria(),
            permissions=SUPER_ADMIN,
            user_token=USER_TOKEN,
        )

        assert len(fake.requests) == 1
        request = fake.requests[0]
        # Participant field: resolved on the wide table.
        assert request.url.path == f"/{self.WIDE}"
        assert request.url.params["select"] == "id_cras,nome_cras,count()"
        assert "protocolo_secretaria" not in request.url.params
        assert request.headers["authorization"] == f"Bearer {USER_TOKEN}"

        assert [o.id for o in options] == ["1"]
        assert options[0].label == "CRAS Centro"

    @pytest.mark.asyncio
    async def test_scalar_and_pair_fields(self, make_repo):
        repo, fake = make_repo(self.make_rows())

        bairros = await repo.get_filter_options(
            field="bairros", filters=FilterCriteria(), permissions=SUPER_ADMIN
        )
        assert [o.id for o in bairros] == ["Bangu", "Centro"]
        assert fake.requests[0].url.path == f"/{self.WIDE}"

        # protocolo_descricoes: single-row 14-column count aggregate over the
        # wide table; labels from the backend map.
        descricoes = await repo.get_filter_options(
            field="protocolo_descricoes",
            filters=FilterCriteria(),
            permissions=SUPER_ADMIN,
        )
        assert len(fake.requests) == 2
        descricao_req = fake.requests[1]
        assert descricao_req.url.path == f"/{self.WIDE}"
        assert descricao_req.url.params["select"] == ",".join(
            f"{column}:{column}.count()" for column in PROTOCOLO_STATUS_COLUMNS
        )
        assert [o.id for o in descricoes] == [
            "sms_vacinacao_pentavalente",
            "smas_acesso_alimentacao",
            "sme_frequencia_escolar",
        ]
        assert all(o.label == PROTOCOLO_DESCRICOES[o.id] for o in descricoes)

        # protocolo_status_list is static: no DB query.
        status = await repo.get_filter_options(
            field="protocolo_status_list",
            filters=FilterCriteria(),
            permissions=SUPER_ADMIN,
        )
        assert len(fake.requests) == 2  # no new request
        assert [o.id for o in status] == ["Atenção", "Irregular", "Regular"]

        bolsa = await repo.get_filter_options(
            field="bolsa_familia", filters=FilterCriteria(), permissions=SUPER_ADMIN
        )
        assert [(o.id, o.label) for o in bolsa] == [
            ("true", "Com Bolsa Família"),
            ("false", "Sem Bolsa Família"),
        ]

        secretarias = await repo.get_filter_options(
            field="protocolo_secretarias",
            filters=FilterCriteria(),
            permissions=SUPER_ADMIN,
        )
        # Single-row per-secretaria counter maxima over the wide table.
        secretaria_req = fake.requests[-1]
        assert secretaria_req.url.path == f"/{self.WIDE}"
        assert secretaria_req.url.params["select"] == (
            "educacao_protocolos_total:educacao_protocolos_total.max(),"
            "assistencia_protocolos_total:assistencia_protocolos_total.max(),"
            "saude_protocolos_total:saude_protocolos_total.max()"
        )
        assert [(o.id, o.label) for o in secretarias] == [
            ("SME", "Educação (SME)"),
            ("SMAS", "Assistência (SMAS)"),
            ("SMS", "Saúde (SMS)"),
        ]

    @pytest.mark.asyncio
    async def test_descricoes_filtered_by_secretaria_cascade(self, make_repo):
        repo, fake = make_repo(self.make_rows())

        sms_only = await repo.get_filter_options(
            field="protocolo_descricoes",
            filters=FilterCriteria(protocolo_secretaria="SMS"),
            permissions=SUPER_ADMIN,
        )
        assert len(fake.requests) == 1
        request = fake.requests[0]
        assert request.url.path == f"/{self.WIDE}"
        assert request.url.params["or"] == "(saude_protocolos_total.gt.0)"
        assert [o.id for o in sms_only] == ["sms_vacinacao_pentavalente"]

        multi = await repo.get_filter_options(
            field="protocolo_descricoes",
            filters=FilterCriteria(protocolo_secretaria="SMS|SME"),
            permissions=SUPER_ADMIN,
        )
        assert fake.requests[1].url.params["or"] == (
            "(saude_protocolos_total.gt.0,educacao_protocolos_total.gt.0)"
        )
        assert [o.id for o in multi] == [
            "sms_vacinacao_pentavalente",
            "sme_frequencia_escolar",
        ]

    @pytest.mark.asyncio
    async def test_descricoes_partial_access_drops_protocols_outside_secretaria(
        self, make_repo
    ):
        # Production-like row: the participant carries protocols of several
        # secretarias while the user can only access SMAS — the row-level or
        # filter alone is not enough, the options must be restricted too.
        rows = {
            self.WIDE: [
                filtro_row(
                    "1",
                    smas_acesso_alimentacao="Atenção",
                    sms_vacinacao_pentavalente="Regular",
                    assistencia_protocolos_total=1,
                ),
            ]
        }
        repo, fake = make_repo(rows)

        descricoes = await repo.get_filter_options(
            field="protocolo_descricoes",
            filters=FilterCriteria(),
            permissions=PARTIAL_SMAS,
        )
        assert [o.id for o in descricoes] == ["smas_acesso_alimentacao"]

    @pytest.mark.asyncio
    async def test_descricoes_full_access_secretaria_filter_drops_others(
        self, make_repo
    ):
        rows = {
            self.WIDE: [
                filtro_row(
                    "1",
                    smas_acesso_alimentacao="Atenção",
                    sms_vacinacao_pentavalente="Regular",
                    assistencia_protocolos_total=1,
                ),
            ]
        }
        repo, fake = make_repo(rows)

        descricoes = await repo.get_filter_options(
            field="protocolo_descricoes",
            filters=FilterCriteria(protocolo_secretaria="SMAS"),
            permissions=SUPER_ADMIN,
        )
        assert [o.id for o in descricoes] == ["smas_acesso_alimentacao"]

    @pytest.mark.asyncio
    async def test_descricoes_cascade_applies_status_and_scalar_filters(
        self, make_repo
    ):
        repo, fake = make_repo(self.make_rows())

        descricoes = await repo.get_filter_options(
            field="protocolo_descricoes",
            filters=FilterCriteria(protocolo_status="Atenção", bairro="Centro"),
            permissions=SUPER_ADMIN,
        )
        request = fake.requests[0]
        assert request.url.path == f"/{self.WIDE}"
        # Cascade: only the field's own filter is excluded; the status (or
        # over the 14 columns) and scalar filters narrow the view.
        assert request.url.params["bairro"] == "ilike.Centro"
        or_param = request.url.params["or"]
        assert len(or_param.strip("()").split(",")) == len(PROTOCOLO_STATUS_COLUMNS)
        assert all(term.endswith(".eq.Atenção") for term in or_param.strip("()").split(","))
        assert [o.id for o in descricoes] == ["smas_acesso_alimentacao"]

    @pytest.mark.asyncio
    async def test_partial_secretaria_restricts_query_and_options(self, make_repo):
        repo, fake = make_repo(self.make_rows())

        bairros = await repo.get_filter_options(
            field="bairros",
            filters=FilterCriteria(),
            permissions=PARTIAL_SMS,
            user_token=USER_TOKEN,
        )
        assert len(fake.requests) == 1
        # Participant field: restriction via or on the pre-aggregated counters.
        assert fake.requests[0].url.path == f"/{self.WIDE}"
        assert fake.requests[0].url.params["or"] == "(saude_protocolos_total.gt.0)"
        assert "protocolo_secretaria" not in fake.requests[0].url.params
        assert [o.id for o in bairros] == ["Bangu", "Centro"]

        descricoes = await repo.get_filter_options(
            field="protocolo_descricoes",
            filters=FilterCriteria(),
            permissions=PARTIAL_SMS,
        )
        descricao_req = fake.requests[1]
        assert descricao_req.url.path == f"/{self.WIDE}"
        assert descricao_req.url.params["or"] == "(saude_protocolos_total.gt.0)"
        assert [o.id for o in descricoes] == ["sms_vacinacao_pentavalente"]

        secretarias = await repo.get_filter_options(
            field="protocolo_secretarias",
            filters=FilterCriteria(),
            permissions=PARTIAL_SMS,
        )
        assert [o.id for o in secretarias] == ["SMS"]

    @pytest.mark.asyncio
    async def test_guards_skip_queries(self, make_repo):
        repo, fake = make_repo(self.make_rows())

        situacoes = await repo.get_filter_options(
            field="situacoes",
            filters=FilterCriteria(),
            permissions=PARTIAL_SMS,
        )
        assert situacoes == []
        assert len(fake.requests) == 0

        descricoes = await repo.get_filter_options(
            field="protocolo_descricoes",
            filters=FilterCriteria(),
            permissions=NO_ACCESS,
        )
        assert descricoes == []
        assert len(fake.requests) == 0

    @pytest.mark.asyncio
    async def test_no_access_participant_fields_without_secretaria_where(
        self, make_repo
    ):
        repo, fake = make_repo(self.make_rows())
        bairros = await repo.get_filter_options(
            field="bairros",
            filters=FilterCriteria(),
            permissions=NO_ACCESS,
        )
        assert len(fake.requests) == 1
        assert "protocolo_secretaria" not in fake.requests[0].url.params
        assert "or" not in fake.requests[0].url.params
        assert [o.id for o in bairros] == ["Bangu", "Centro"]

    @pytest.mark.asyncio
    async def test_cascade_excludes_own_filter_and_keeps_search(self, make_repo):
        repo, fake = make_repo(self.make_rows())

        bairros = await repo.get_filter_options(
            field="bairros",
            filters=FilterCriteria(bairro="Centro", search="ANA"),
            permissions=SUPER_ADMIN,
        )
        request = fake.requests[0]
        assert "bairro" not in request.url.params  # own filter excluded
        assert "or" in request.url.params  # search still applied
        assert [o.id for o in bairros] == ["Bangu", "Centro"]

        cras = await repo.get_filter_options(
            field="cras",
            filters=FilterCriteria(bairro="Centro", search="ANA"),
            permissions=SUPER_ADMIN,
        )
        request = fake.requests[1]
        assert request.url.params["bairro"] == "ilike.Centro"
        assert "or" in request.url.params
        assert [o.id for o in cras] == ["1"]

    @pytest.mark.asyncio
    async def test_protocol_filter_cascade_excludes_own_field(self, make_repo):
        repo, fake = make_repo(self.make_rows())

        secretarias = await repo.get_filter_options(
            field="protocolo_secretarias",
            filters=FilterCriteria(protocolo_secretaria="SMS"),
            permissions=SUPER_ADMIN,
        )
        # Own filter dropped: all present secretarias remain selectable.
        assert [o.id for o in secretarias] == ["SME", "SMAS", "SMS"]

        bairros = await repo.get_filter_options(
            field="bairros",
            filters=FilterCriteria(protocolo_secretaria="SMS"),
            permissions=SUPER_ADMIN,
        )
        # Participant field with an active protocol filter: the wide query
        # keeps the secretaria counter restriction.
        request = fake.requests[1]
        assert request.url.path == f"/{self.WIDE}"
        assert request.url.params["or"] == "(saude_protocolos_total.gt.0)"
        assert [o.id for o in bairros] == ["Bangu", "Centro"]

    @pytest.mark.asyncio
    async def test_cache_miss_writes_and_hit_skips_fetches(self, make_repo):
        redis = MagicMock()
        redis.get = AsyncMock(return_value=None)
        redis.set = AsyncMock()
        repo, fake = make_repo(self.make_rows(), redis_client=redis)

        options = await repo.get_filter_options(
            field="bairros", filters=FilterCriteria(), permissions=SUPER_ADMIN
        )
        assert len(fake.requests) == 1
        redis.set.assert_awaited_once()

        redis.get = AsyncMock(
            return_value=json.dumps(
                [opt.model_dump(mode="json") for opt in options]
            ).encode()
        )
        cached = await repo.get_filter_options(
            field="bairros", filters=FilterCriteria(), permissions=SUPER_ADMIN
        )
        assert len(fake.requests) == 1  # no new requests on hit
        assert [opt.model_dump() for opt in cached] == [
            opt.model_dump() for opt in options
        ]

    @pytest.mark.asyncio
    async def test_cache_key_isolates_users_and_fields(self, make_repo):
        redis = MagicMock()
        redis.get = AsyncMock(return_value=None)
        redis.set = AsyncMock()
        repo, _ = make_repo(self.make_rows(), redis_client=redis)

        await repo.get_filter_options(
            field="bairros", filters=FilterCriteria(), permissions=SUPER_ADMIN
        )
        await repo.get_filter_options(
            field="bairros", filters=FilterCriteria(), permissions=PARTIAL_SMS
        )
        await repo.get_filter_options(
            field="cras", filters=FilterCriteria(), permissions=SUPER_ADMIN
        )

        keys = [call.args[0] for call in redis.set.await_args_list]
        assert len(keys) == 3
        assert len(set(keys)) == 3
        assert all(key.startswith("filters_v2:") for key in keys)

    @pytest.mark.asyncio
    async def test_bypass_cache_skips_read_still_writes(self, make_repo):
        redis = MagicMock()
        redis.get = AsyncMock(return_value=None)
        redis.set = AsyncMock()
        repo, fake = make_repo(self.make_rows(), redis_client=redis)

        await repo.get_filter_options(
            field="bairros",
            filters=FilterCriteria(),
            permissions=SUPER_ADMIN,
            bypass_cache=True,
        )
        assert len(fake.requests) == 1
        redis.get.assert_not_awaited()
        redis.set.assert_awaited_once()


# ---------------------------------------------------------------------------
# Export (CSV) - wide rows, access-scoped columns, parallel prefetch
# ---------------------------------------------------------------------------


FULL_NON_SUPER = UserPermissions(
    cpf="55555555555",
    is_admin=True,
    is_super_admin=False,
    secretarias_acesso=["SME", "SMS", "SMAS"],
)


async def _export_pages(
    repo,
    filters: FilterCriteria | None = None,
    sort: SortParams | None = None,
    permissions=SUPER_ADMIN,
) -> list[list[dict]]:
    return [
        page
        async for page in repo.export_wide_rows(
            filters=filters or FilterCriteria(),
            sort=sort or SortParams(),
            permissions=permissions,
            user_token=USER_TOKEN,
        )
    ]


@pytest.mark.asyncio
async def test_export_super_admin_selects_all_and_keeps_every_column(make_repo):
    rows = [
        wide_row(
            "1",
            latitude=-22.867801,
            longitude=-43.2931916,
            protocolos={"sms_vacinacao_pentavalente": "Regular"},
        ),
        wide_row("2", latitude=-22.9, longitude=-43.3),
    ]
    repo, fake = make_repo({"endpoint_participante_protocolos_wide": rows})

    pages = await _export_pages(repo)

    assert [row["id_membro_familia"] for row in pages[0]] == ["1", "2"]
    assert pages[0][0]["latitude"] == -22.867801
    assert pages[0][0]["longitude"] == -43.2931916
    assert pages[0][0]["sms_vacinacao_pentavalente"] == "Regular"
    assert pages[0][0]["situacao"] == "Atenção"
    assert all(req.url.params.get("select") == "*" for req in fake.requests)


@pytest.mark.asyncio
async def test_export_non_super_admin_full_access_hides_coordinates(make_repo):
    rows = [
        wide_row("1", latitude=-22.867801, longitude=-43.2931916),
    ]
    repo, _ = make_repo({"endpoint_participante_protocolos_wide": rows})

    pages = await _export_pages(repo, permissions=FULL_NON_SUPER)

    row = pages[0][0]
    assert "latitude" not in row
    assert "longitude" not in row
    # Everything else stays (full protocol access).
    assert row["situacao"] == "Atenção"
    assert row["saude_protocolos_total"] == 4


@pytest.mark.asyncio
async def test_export_partial_access_strips_other_secretarias_and_globals(make_repo):
    rows = [
        wide_row(
            "1",
            latitude=-22.867801,
            longitude=-43.2931916,
            protocolos={
                "sms_vacinacao_pentavalente": "Regular",
                "smas_acesso_alimentacao": "Regular",
            },
        ),
    ]
    repo, _ = make_repo({"endpoint_participante_protocolos_wide": rows})

    pages = await _export_pages(repo, permissions=PARTIAL_SMS)

    row = pages[0][0]
    # Allowed secretaria columns are kept.
    assert row["saude_protocolos_total"] == 4
    assert row["saude_fracao"] == "4/4"
    assert row["sms_vacinacao_pentavalente"] == "Regular"
    # Disallowed secretaria counters/fractions and protocol columns are gone.
    for column in (
        "assistencia_protocolos_total",
        "assistencia_fracao",
        "educacao_protocolos_total",
        "educacao_fracao",
        "smas_acesso_alimentacao",
    ):
        assert column not in row
    # Global protocol-derived columns are omitted for partial access.
    for column in ("situacao", "total_fracao", "total_protocolos"):
        assert column not in row
    # Coordinates are super-admin only.
    assert "latitude" not in row
    assert "longitude" not in row
    # Base participant columns stay.
    assert row["nome"] == "NOME 1"


@pytest.mark.asyncio
async def test_export_partial_access_restricts_rows_to_accessible_secretaria(
    make_repo,
):
    rows = [
        wide_row("1", saude_protocolos_total=4),
        wide_row("2", saude_protocolos_total=0),
    ]
    repo, fake = make_repo({"endpoint_participante_protocolos_wide": rows})

    pages = await _export_pages(repo, permissions=PARTIAL_SMS)

    assert [row["id_membro_familia"] for row in pages[0]] == ["1"]
    assert any(
        "saude_protocolos_total.gt.0" in req.url.params.get("or", "")
        for req in fake.requests
    )


@pytest.mark.asyncio
async def test_export_no_access_with_protocol_filter_is_empty(make_repo):
    repo, fake = make_repo(
        {"endpoint_participante_protocolos_wide": [wide_row("1")]}
    )

    pages = await _export_pages(
        repo,
        filters=FilterCriteria(protocolo_status="Regular"),
        permissions=NO_ACCESS,
    )

    assert pages == []
    assert fake.requests == []


@pytest.mark.asyncio
async def test_export_forced_protocol_outside_access_raises_forbidden(make_repo):
    repo, _ = make_repo(
        {"endpoint_participante_protocolos_wide": [wide_row("1")]}
    )

    with pytest.raises(ForbiddenError):
        await _export_pages(
            repo,
            filters=FilterCriteria(protocolo_descricao="smas_acesso_alimentacao"),
            permissions=PARTIAL_SMS,
        )


@pytest.mark.asyncio
async def test_export_unknown_protocol_raises_validation_error(make_repo):
    repo, _ = make_repo(
        {"endpoint_participante_protocolos_wide": [wide_row("1")]}
    )

    with pytest.raises(ValidationError):
        await _export_pages(
            repo,
            filters=FilterCriteria(protocolo_descricao="protocolo_inventado"),
            permissions=SUPER_ADMIN,
        )


@pytest.mark.asyncio
async def test_export_multipage_prefetch_preserves_order(make_repo):
    rows = [wide_row(str(i)) for i in range(1005)]
    repo, fake = make_repo({"endpoint_participante_protocolos_wide": rows})

    pages = await _export_pages(repo)

    ids = [row["id_membro_familia"] for page in pages for row in page]
    assert ids == [str(i) for i in range(1005)]
    assert [len(page) for page in pages] == [1000, 5]
    # One prefetch window of 3 pages (the third is empty and ends the loop).
    assert len(fake.requests) == 3


@pytest.mark.asyncio
async def test_export_generator_can_cross_task_boundaries(make_repo):
    rows = [wide_row(str(i)) for i in range(1005)]
    repo, fake = make_repo({"endpoint_participante_protocolos_wide": rows})

    generator = repo.export_wide_rows(
        filters=FilterCriteria(),
        sort=SortParams(),
        permissions=SUPER_ADMIN,
        user_token=USER_TOKEN,
    )

    # First page is consumed in this task (like the use case prefetch)...
    first_page = await anext(generator)
    assert len(first_page) == 1000

    # ...the rest is drained from a different task (like the
    # StreamingResponse), which used to blow up the ContextVar reset.
    async def _drain() -> list[dict]:
        drained: list[dict] = []
        async for page in generator:
            drained.extend(page)
        return drained

    remaining = await asyncio.gather(_drain())

    assert len(remaining[0]) == 5
    assert len(fake.requests) == 3
