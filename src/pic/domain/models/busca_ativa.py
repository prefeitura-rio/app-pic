"""Eventos de busca ativa do participante (`endpoint_busca_ativa`).

One entry per busca ativa event (grain: participant x event). Events come
from two sources (`fonte`): SMS (health home-visits) and SMAS (assistência
social searches). The SMAS-specific fields are null/empty for SMS events and
vice-versa — see schema.json (dicionário de dados).
"""

from datetime import date, datetime

from pydantic import BaseModel, Field


class BuscaAtivaUnidadeSMS(BaseModel):
    """Unidade de saúde (clínica da família/equipe) da busca ativa SMS."""

    nome: str | None = None
    regional: str | None = None
    equipe_nome: str | None = None


class BuscaAtivaUnidadeSMAS(BaseModel):
    """Equipamento de assistência social (CRAS/CAS) da busca ativa SMAS."""

    nome: str | None = None
    regional: str | None = None


class BuscaAtivaUnidadeReferenciada(BaseModel):
    """Unidade responsável pela busca ativa (sme não é exposto pela API)."""

    sms: BuscaAtivaUnidadeSMS | None = None
    smas: BuscaAtivaUnidadeSMAS | None = None


class BuscaAtivaEvento(BaseModel):
    """One busca ativa event for the participant."""

    id_busca_ativa: str | None = None
    fonte: str | None = None
    data: date | None = None
    sms_tipo_publico: str | None = None
    smas_tipo: list[str] = Field(default_factory=list)
    smas_familia_localizada_indicador: bool | None = None
    smas_protocolo_violado: list[str] = Field(default_factory=list)
    smas_motivo_nao_localizada: list[str] = Field(default_factory=list)
    processed_at: datetime | None = None
    unidade_referenciada: BuscaAtivaUnidadeReferenciada | None = None
