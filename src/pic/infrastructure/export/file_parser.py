"""CSV/XLSX parsing for the admin user-import flow (IUserImportFileParser)."""

import io

import polars as pl

from src.pic.application.ports.user_import_parser import IUserImportFileParser
from src.pic.domain.errors import ValidationError

_MAX_ROWS = 1000


class UserImportFileParser(IUserImportFileParser):
    def parse(self, filename: str, content: bytes) -> pl.DataFrame:
        if not filename:
            raise ValidationError("Nome do arquivo nao informado")

        filename_lower = filename.lower()
        if not (filename_lower.endswith(".csv") or filename_lower.endswith(".xlsx")):
            raise ValidationError("Formato de arquivo invalido. Use CSV ou XLSX.")

        try:
            if filename_lower.endswith(".csv"):
                try:
                    df = pl.read_csv(io.BytesIO(content))
                except Exception:
                    df = pl.read_csv(io.BytesIO(content), encoding="latin1")
            else:
                import pandas as pd

                df = pl.from_pandas(pd.read_excel(io.BytesIO(content), engine="openpyxl"))
        except Exception as exc:
            raise ValidationError(f"Nao foi possivel ler o arquivo: {exc}") from exc

        if "cpf" not in df.columns:
            raise ValidationError("Coluna 'cpf' nao encontrada no arquivo")

        if len(df) > _MAX_ROWS:
            raise ValidationError(
                f"Arquivo contem {len(df)} linhas. Maximo permitido: {_MAX_ROWS}"
            )

        return df
