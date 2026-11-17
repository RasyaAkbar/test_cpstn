from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.data.models import DATASET_TABLES, DatasetImport
from app.modules.data.schemas import DatasetImportInfo, DatasetStatus, TableCount


def get_dataset_status(db: Session) -> DatasetStatus:
    latest = db.scalars(
        select(DatasetImport).order_by(DatasetImport.import_id.desc()).limit(1)
    ).first()
    tables = [
        TableCount(table=table.name, rows=db.scalar(select(func.count()).select_from(table)))
        for table in DATASET_TABLES
    ]
    return DatasetStatus(
        latest_import=None
        if latest is None
        else DatasetImportInfo(
            import_id=latest.import_id,
            source_file=latest.source_file,
            file_sha256=latest.file_sha256,
            data_source=latest.data_source,
            imported_at=latest.imported_at,
        ),
        tables=tables,
    )
