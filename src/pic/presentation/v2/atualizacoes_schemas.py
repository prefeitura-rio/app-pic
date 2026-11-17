"""Schemas HTTP do Painel de Atualizações (``/api/v2/dashboard/atualizacoes-regionais``).

**Contrato congelado** (etapa B2): esta superfície é a fonte da verdade do
contrato do painel; ``types.ts`` do frontend é um **espelho** — campo novo no
front só entra passando por aqui, e mudança de contrato congelado entra apenas
como campo novo opcional, nunca como renomeação.

Mesmo padrão de ``monitoring_schemas.py``: os modelos vivem no domínio
(``domain/models/atualizacoes.py``) e são re-exportados aqui para o OpenAPI.
"""

from src.pic.domain.models.atualizacoes import (
    AtualizacoesMeta,
    AtualizacoesPainelData,
    AtualizacoesRegionaisResponse,
    Contexto,
    FocoIrregularidade,
    MetaCard,
    MetricaVariacao,
    ProtocoloVariacao,
    Regularidade,
    SeriePonto,
)

__all__ = [
    "AtualizacoesMeta",
    "AtualizacoesPainelData",
    "AtualizacoesRegionaisResponse",
    "Contexto",
    "FocoIrregularidade",
    "MetaCard",
    "MetricaVariacao",
    "ProtocoloVariacao",
    "Regularidade",
    "SeriePonto",
]
