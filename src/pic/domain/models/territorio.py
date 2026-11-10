"""Constantes territoriais e normalizadores compartilhados (mapa + Acompanhamento).

Centraliza o que ``get_regularidade_por_camada``, ``get_detalhes_regiao`` e
``get_monitoring`` usavam duplicado/privado:

- ``CAMADAS_SUPORTADAS`` — camadas territoriais aceitas pelos endpoints.
- ``CAMADA_COLUMN`` — camada → coluna RAW do recorte territorial (a mesma
  chave de GROUP BY que o geospatial usava como ``CAMADA_GROUP_COLUMN``).
- ``NORMALIZERS`` — camada → normalizador da chave de join (o mapa exibe o
  valor exibido; o backend resolve o RAW pelo join normalizado).
"""

import re
import unicodedata
from collections.abc import Callable

CAMADAS_SUPORTADAS = ("bairro", "ra", "cas", "cre", "ap")

CAMADA_COLUMN: dict[str, str] = {
    "bairro": "bairro",
    "ra": "regiao_administrativa",
    "cas": "id_cas",
    "cre": "id_cre",
    "ap": "id_ap",
}

# Prefixo de ordinal do consolidado em RA ("3ª Rio Comprido" → "Rio Comprido").
_ORDINAL_PREFIX_RE = re.compile(r"^\d+\s*ª\s*")

# Só dígitos (para joins por código das camadas estáticas).
_DIGITOS_RE = re.compile(r"\D")

# Grafias divergentes do consolidado → datario (mesmo padrão de "Portuaria").
# A chave/valor já estão normalizados.
_RA_NOME_ALIASES: dict[str, str] = {
    "santa tereza": "santa teresa",
}


def normalize_bairro_nome(nome: str | None) -> str:
    """Normaliza nome de região para join: sem acentos, lowercase, sem espaços extras."""
    if not nome:
        return ""
    decomposed = unicodedata.normalize("NFKD", str(nome))
    ascii_only = "".join(c for c in decomposed if not unicodedata.combining(c))
    return ascii_only.strip().lower()


def normalize_ra_nome(nome: str | None) -> str:
    """Normaliza nome de RA removendo o ordinal ("3ª ") e aplicando aliases de grafia."""
    normalized = normalize_bairro_nome(_ORDINAL_PREFIX_RE.sub("", nome or ""))
    return _RA_NOME_ALIASES.get(normalized, normalized)


def normalize_codigo(codigo: str | None) -> str:
    """Chave de join por código: só dígitos, sem zeros à esquerda.

    Absorve as diferenças de formato entre consolidado e camadas do data.rio:
    ``"01ª CAS"`` → ``"1"`` (vs ``cas_label`` ``"1ª CAS"`` → ``"1"``),
    ``"AP 3.1"`` → ``"31"`` (vs ``id_ap`` ``"31"``), ``"01"`` → ``"1"``.
    ``"0"``/``"SEM VÍNCULO"`` → ``""`` (nunca casa → fica no meta).
    """
    return _DIGITOS_RE.sub("", str(codigo or "")).lstrip("0")


NORMALIZERS: dict[str, Callable[[str | None], str]] = {
    "bairro": normalize_bairro_nome,
    "ra": normalize_ra_nome,
    "cas": normalize_codigo,
    "cre": normalize_codigo,
    "ap": normalize_codigo,
}
