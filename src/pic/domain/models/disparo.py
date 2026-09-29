"""Disparos de WhatsApp (HSM Salesforce) do participante.

One entry per campaign the participant received (`endpoint_whatsapp_disparo`
grain: participant x campaign): the latest disparo of the campaign plus the
30-day counters. Every field is nullable — a row may carry no disparo or
partial data (see REFINAMENTO.md, dicionário de dados).
"""

from datetime import date, datetime

from pydantic import BaseModel


class DisparoMetadados(BaseModel):
    """30-day counters of one campaign's disparos."""

    total_ultimos_30d: int | None = None
    entregues_30d: int | None = None
    falhas_30d: int | None = None


class Disparo(BaseModel):
    """One campaign's latest disparo for the participant."""

    campanha: str | None = None
    data: date | None = None
    datahora: datetime | None = None
    secretaria: str | None = None
    status: str | None = None
    indicador_falha: bool | None = None
    metadados: DisparoMetadados | None = None
