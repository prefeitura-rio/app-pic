import pytest

from src.pic.domain.models.filters import (
    FilterCascade,
    FilterCriteria,
    FilterOption,
)
from src.pic.domain.models.pagination import (
    PaginationMeta,
)
from src.pic.domain.models.participante import ParticipanteListItem


@pytest.fixture
def sample_participante_list_item() -> ParticipanteListItem:
    return ParticipanteListItem(
        id_familia="FAM123",
        id_membro_familia="MEM456",
        nome="Maria Silva",
        cpf="12345678900",
        grupo="crianca_bf_0_3",
        bairro="Centro",
        idade=2,
        status="ativo",
        situacao="irregular",
        total_fracao="3/5",
        assistencia_fracao="1/2",
        educacao_fracao="1/1",
        saude_fracao="1/2",
    )


@pytest.fixture
def sample_filter_criteria() -> FilterCriteria:
    return FilterCriteria(bairro="centro", grupo="crianca_bf_0_3")


@pytest.fixture
def sample_cascade() -> FilterCascade:
    return FilterCascade(
        bairros=[FilterOption(id="centro", label="Centro")],
        grupos=[FilterOption(id="crianca_bf_0_3", label="Crianca 0-3 (BF)")],
    )


@pytest.fixture
def sample_meta() -> PaginationMeta:
    return PaginationMeta(
        page=1,
        page_size=20,
        total_rows=100,
        total_pages=5,
        cache_hit=True,
    )
