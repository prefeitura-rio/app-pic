"""Disparos de WhatsApp (HSM Salesforce) do participante.

One entry per campaign the participant received (`endpoint_whatsapp_disparo`
grain: participant x campaign x window): the latest disparo of the campaign
plus the 240-day counters. Every field is nullable — a row may carry no
disparo or partial data (see REFINAMENTO.md, dicionário de dados).
"""

from datetime import date, datetime

from pydantic import BaseModel

# Janela canônica (em dias) dos disparos exibidos no app. O mart
# `endpoint_whatsapp_disparo` grava 5 janelas por disparo (30/60/120/180/240);
# o app lê somente esta, combinada com `disparo_na_janela_indicador = true`.
DISPARO_JANELA_DIAS = 240


class DisparoMetadados(BaseModel):
    """Contadores da janela de 240 dias de uma campanha de disparos."""

    total_ultimos_240d: int | None = None
    entregues_240d: int | None = None
    falhas_240d: int | None = None


class Disparo(BaseModel):
    """One campaign's latest disparo for the participant."""

    campanha: str | None = None
    data: date | None = None
    datahora: datetime | None = None
    secretaria: str | None = None
    status: str | None = None
    indicador_falha: bool | None = None
    metadados: DisparoMetadados | None = None
