from typing import List, Optional, TypeVar, Generic, Any
from pydantic import BaseModel
from datetime import date, datetime

T = TypeVar('T')

class PaginationMeta(BaseModel):
    page: int
    page_size: int
    total_rows: int
    total_pages: int
    cache_hit: bool
    profiling: Optional[Any] = None

class PaginatedResponse(BaseModel, Generic[T]):
    data: List[T]
    meta: PaginationMeta

# Shared / Nested Models

class DistribuicaoMotivoSaida(BaseModel):
    motivo: Optional[str] = None
    total: Optional[int] = None

class DistribuicaoGrupo(BaseModel):
    grupo: Optional[str] = None
    total_participantes: Optional[int] = None

class DistribuicaoBairro(BaseModel):
    bairro: Optional[str] = None
    total_participantes: Optional[int] = None

class DistribuicaoSafra(BaseModel):
    safra: Optional[date] = None
    total_participantes: Optional[int] = None

# Endpoint Models

class EvolucaoSafra(BaseModel):
    safra: Optional[date] = None
    total_entrada: Optional[int] = None
    total_ativos: Optional[int] = None
    total_inativos: Optional[int] = None
    distribuicao_motivo_saida: List[DistribuicaoMotivoSaida] = []
    data_atualizacao: Optional[datetime] = None

class ProtocoloDetalhes(BaseModel):
    cpf: Optional[str] = None
    id_membro_familia: Optional[str] = None
    nome: Optional[str] = None
    grupo: Optional[str] = None
    protocolo_id: Optional[str] = None
    protocolo_secretaria: Optional[str] = None
    protocolo_descricao: Optional[str] = None
    protocolo_level: Optional[str] = None
    protocolo_status: Optional[str] = None
    protocolo_violado: Optional[bool] = None
    protocolo_data_referencia_particicao: Optional[date] = None
    protocolo_status_label: Optional[str] = None
    cpf_particao: Optional[int] = None

class ProtocoloResumo(BaseModel):
    protocolo_secretaria: Optional[str] = None
    protocolo_id: Optional[str] = None
    protocolo_descricao: Optional[str] = None
    protocolo_level: Optional[str] = None
    total_participantes: Optional[int] = None
    total_violados: Optional[int] = None
    total_regular: Optional[int] = None
    total_nao_aplica: Optional[int] = None
    percentual_violados: Optional[float] = None
    nivel_prioridade: Optional[str] = None
    data_atualizacao: Optional[datetime] = None

class Dashboard(BaseModel):
    total_participantes_ativos: Optional[int] = None
    total_participantes_inativos: Optional[int] = None
    total_participantes_geral: Optional[int] = None
    total_participantes_em_atencao: Optional[int] = None
    percentual_em_atencao: Optional[float] = None
    total_protocolos: Optional[int] = None
    total_protocolos_violados: Optional[int] = None
    percentual_protocolos_violados: Optional[float] = None
    total_protocolos_smas: Optional[int] = None
    total_protocolos_smas_violados: Optional[int] = None
    percentual_smas_violados: Optional[float] = None
    total_protocolos_sme: Optional[int] = None
    total_protocolos_sme_violados: Optional[int] = None
    percentual_sme_violados: Optional[float] = None
    total_protocolos_sms: Optional[int] = None
    total_protocolos_sms_violados: Optional[int] = None
    percentual_sms_violados: Optional[float] = None
    distribuicao_por_grupo: List[DistribuicaoGrupo] = []
    top_bairros: List[DistribuicaoBairro] = []
    distribuicao_motivo_saida: List[DistribuicaoMotivoSaida] = []
    distribuicao_por_safra: List[DistribuicaoSafra] = []
    data_atualizacao: Optional[datetime] = None

class FiltroRegional(BaseModel):
    id: Optional[str] = None
    nome: Optional[str] = None
    tipo: Optional[str] = None
    secretaria: Optional[str] = None
    bairros: List[str] = []
    data_atualizacao: Optional[datetime] = None

class FiltroEquipamento(BaseModel):
    id: Optional[str] = None
    nome: Optional[str] = None
    tipo: Optional[str] = None
    secretaria: Optional[str] = None
    id_regional: Optional[str] = None
    cep: Optional[str] = None
    bairro: Optional[str] = None
    data_atualizacao: Optional[datetime] = None

class Participante(BaseModel):
    cpf: Optional[str] = None
    id_membro_familia: Optional[str] = None
    nome: Optional[str] = None
    sexo: Optional[str] = None
    nascimento_data: Optional[date] = None
    idade: Optional[int] = None
    grupo: Optional[str] = None
    cohort: Optional[date] = None
    status: Optional[str] = None
    status_inativo_motivo: Optional[str] = None
    bairro: Optional[str] = None
    logradouro: Optional[str] = None
    numero: Optional[str] = None
    cep: Optional[str] = None
    telefone_principal: Optional[str] = None
    email_principal: Optional[str] = None
    total_protocolos_violados: Optional[int] = None
    total_protocolos: Optional[int] = None
    total_fracao: Optional[str] = None
    assistencia_protocolos_violados: Optional[int] = None
    assistencia_protocolos_total: Optional[int] = None
    assistencia_fracao: Optional[str] = None
    educacao_protocolos_violados: Optional[int] = None
    educacao_protocolos_total: Optional[int] = None
    educacao_fracao: Optional[str] = None
    saude_protocolos_violados: Optional[int] = None
    saude_protocolos_total: Optional[int] = None
    saude_fracao: Optional[str] = None
    situacao: Optional[str] = None
    cadunico_indicador: Optional[bool] = None
    bolsa_familia_indicador: Optional[bool] = None
    bolsa_familia_valor: Optional[float] = None
    id_cras: Optional[str] = None
    nome_cras: Optional[str] = None
    id_escola: Optional[str] = None
    nome_escola: Optional[str] = None
    id_cre: Optional[str] = None
    frequencia_escolar_percentual: Optional[float] = None
    id_clinica_familia: Optional[str] = None
    nome_clinica_familia: Optional[str] = None
    cpf_particao: Optional[int] = None
