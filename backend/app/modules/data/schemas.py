from datetime import datetime

from pydantic import BaseModel


class TableCount(BaseModel):
    table: str
    rows: int


class DatasetImportInfo(BaseModel):
    import_id: int
    source_file: str
    file_sha256: str
    data_source: str
    imported_at: datetime


class DatasetStatus(BaseModel):
    """Dataset baseline yang sedang dimuat. `latest_import` None = belum pernah import."""

    latest_import: DatasetImportInfo | None
    tables: list[TableCount]
