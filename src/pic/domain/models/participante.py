import json
from datetime import date

from pydantic import BaseModel, field_validator

from src.pic.domain.models.endereco import EnderecoSMS
from src.pic.domain.models.protocolo import ProtocoloListagemItem


class ParticipanteListItem(BaseModel):
    id_familia: str | None = None
    id_membro_familia: str | None = None
    nome: str | None = None
    cpf: str | None = None
    grupo: str | None = None
    bairro: str | None = None
    idade: int | None = None
    status: str | None = None
    situacao: str | None = None
    total_fracao: str | None = None
    assistencia_fracao: str | None = None
    educacao_fracao: str | None = None
    saude_fracao: str | None = None


class Participante(BaseModel):
    @field_validator("endereco_sms", mode="before")
    @classmethod
    def parse_endereco_sms(cls, v: object) -> object:
        if isinstance(v, str):
            try:
                return json.loads(v)
            except (json.JSONDecodeError, ValueError):
                return None
        return v

    id_familia: str | None = None
    id_membro_familia: str | None = None
    nome: str | None = None
    cpf: str | None = None
    grupo: str | None = None
    idade: int | None = None
    nascimento_data: date | None = None
    endereco: str | None = None
    complemento: str | None = None
    bairro: str | None = None
    endereco_sms: EnderecoSMS | None = None
    telefone_1_ddd: str | None = None
    telefone_1_numero: str | None = None
    telefone_2_ddd: str | None = None
    telefone_2_numero: str | None = None
    nome_cre: str | None = None
    nome_escola: str | None = None
    source_escola: str | None = None
    nome_cas: str | None = None
    nome_cras: str | None = None
    source_cras: str | None = None
    nome_clinica_familia: str | None = None
    source_clinica_familia: str | None = None
    nome_equipe_familia: str | None = None
    source_equipe_familia: str | None = None
    equipe_familia: str | None = None
    has_bolsa_familia: bool | None = None
    has_cartao_pic: bool | None = None
    cohort: date | None = None
    status: str | None = None
    situacao: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    total_protocolos: int | None = None
    total_protocolos_irregular: int | None = None
    total_protocolos_atencao: int | None = None
    total_protocolos_regular: int | None = None
    total_fracao: str | None = None
    assistencia_protocolos_total: int | None = None
    assistencia_protocolos_irregular: int | None = None
    assistencia_protocolos_atencao: int | None = None
    assistencia_protocolos_regular: int | None = None
    assistencia_fracao: str | None = None
    educacao_protocolos_total: int | None = None
    educacao_protocolos_irregular: int | None = None
    educacao_protocolos_atencao: int | None = None
    educacao_protocolos_regular: int | None = None
    educacao_fracao: str | None = None
    saude_protocolos_total: int | None = None
    saude_protocolos_irregular: int | None = None
    saude_protocolos_atencao: int | None = None
    saude_protocolos_regular: int | None = None
    saude_fracao: str | None = None
    protocolo_listagem: list[ProtocoloListagemItem] | None = None
