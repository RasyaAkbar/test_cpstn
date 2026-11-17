from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.modules.data.schemas import DatasetStatus
from app.modules.data.service import get_dataset_status

router = APIRouter(prefix="/data", tags=["Data"])


@router.get("/status", response_model=DatasetStatus)
def dataset_status(db: Annotated[Session, Depends(get_db)]) -> DatasetStatus:
    """Import dataset terakhir dan jumlah baris tiap tabel baseline."""
    try:
        return get_dataset_status(db)
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database atau tabel dataset belum siap",
        ) from exc
