import json

from pydantic import BaseModel, model_serializer, model_validator


class ProtocoloMotivoDetalhe(BaseModel):
    fonte: str
    data_particao: str | None = None


class ProtocoloMotivo(BaseModel):
    motivos: list[str]
    detalhes: dict[str, ProtocoloMotivoDetalhe] = {}

    @model_validator(mode="before")
    @classmethod
    def parse_json_string(cls, data):
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except (json.JSONDecodeError, ValueError):
                return {}
        if isinstance(data, dict):
            detalhes = data.get("detalhes", {})
            data["detalhes"] = {k: v for k, v in detalhes.items() if v is not None}
        return data


class ProtocoloListagemItem(BaseModel):
    id: str | None = None
    secretaria: str | None = None
    descricao: str | None = None
    status: str | None = None
    irregular_indicador: bool | None = None
    protocolo_status_label: str | None = None
    protocolo_motivo: ProtocoloMotivo | None = None

    @model_serializer(mode="wrap")
    def _drop_none_motivo(self, handler, info):
        result = handler(self, info)
        if result.get("protocolo_motivo") is None:
            result.pop("protocolo_motivo", None)
        return result
