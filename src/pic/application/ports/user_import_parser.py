from abc import ABC, abstractmethod

import polars as pl


class IUserImportFileParser(ABC):
    @abstractmethod
    def parse(self, filename: str, content: bytes) -> pl.DataFrame:
        """Parse an uploaded CSV/XLSX into a Polars DataFrame.

        Raises `ValidationError` (domain) for invalid filename, format or
        content (missing `cpf` column, row limit exceeded).
        """
        ...
