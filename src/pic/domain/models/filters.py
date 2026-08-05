
from pydantic import BaseModel, ConfigDict


class FilterOption(BaseModel):
    id: str
    label: str


class _FilterFields(BaseModel):
    model_config = ConfigDict(extra="ignore")

    bairros: list[FilterOption] = []
    subprefeituras: list[FilterOption] = []
    regioes_administrativas: list[FilterOption] = []
    grupos: list[FilterOption] = []
    cohorts: list[FilterOption] = []
    status_list: list[FilterOption] = []
    situacoes: list[FilterOption] = []
    racas: list[FilterOption] = []
    cres: list[FilterOption] = []
    aps: list[FilterOption] = []
    cas_list: list[FilterOption] = []
    cras: list[FilterOption] = []
    escolas: list[FilterOption] = []
    clinicas: list[FilterOption] = []
    equipes_familia: list[FilterOption] = []
    protocolo_descricoes: list[FilterOption] = []
    protocolo_status_list: list[FilterOption] = []


class FilterCascade(_FilterFields):
    pass


class FilterVocabulary(_FilterFields):
    pass


# --- Request query-param models (domain view of incoming filters) ---


class FilterCriteria(BaseModel):
    subprefeitura: str | None = None
    regiao_administrativa: str | None = None
    bairro: str | None = None
    cre: str | None = None
    ap: str | None = None
    cas: str | None = None
    cras: str | None = None
    escola: str | None = None
    clinica: str | None = None
    equipe_familia: str | None = None
    safra: str | None = None
    grupo: str | None = None
    status: str | None = None
    situacao: str | None = None
    has_bolsa_familia: bool | None = None
    raca: str | None = None
    search: str | None = None
    protocolo_descricao: str | None = None
    protocolo_status: str | None = None
    protocolo_secretaria: str | None = None
