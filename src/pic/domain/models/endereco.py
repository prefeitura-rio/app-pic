from pydantic import BaseModel


class EnderecoSMS(BaseModel):
    endereco: str | None = None
    complemento: str | None = None
    bairro: str | None = None
