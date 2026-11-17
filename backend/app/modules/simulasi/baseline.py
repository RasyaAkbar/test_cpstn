"""Sumber baseline untuk simulasi (langkah 1 desain IV.2.3).

PEMILIK: Orang 2 — Simulasi (Iterasi 1).

Satu-satunya titik masuk baseline: dataset terakhir yang diimpor ke database lewat
`python -m app.modules.data.importer` (lihat db_baseline.py). data_source mengikuti
import tersebut ("synthetic" atau "puti") dan ditampilkan di setiap layar.

Snapshot disimpan per import: selama tidak ada import baru, request berikutnya memakai
snapshot yang sama (frozen, aman dipakai bersama antar request). Kunci memakai juga hash
file dan waktu import, karena import_id bisa berulang jika database dibuat ulang.
"""

from typing import Annotated

from fastapi import Depends, HTTPException, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.modules.simulasi.db_baseline import latest_import, read_rows, snapshot_from_rows
from app.modules.simulasi.domain import Snapshot

NO_DATASET = (
    "Dataset baseline belum diimpor. Dari folder backend/ jalankan: "
    "python -m app.modules.data.importer ../puti_datasets.xlsx --source synthetic"
)

_cache: dict[tuple, Snapshot] = {}


def get_baseline_snapshot(db: Annotated[Session, Depends(get_db)]) -> Snapshot:
    """Dependency FastAPI. 503 jika database belum siap atau dataset belum diimpor."""
    try:
        record = latest_import(db)
        if record is None:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, NO_DATASET)
        key = (record.import_id, record.file_sha256, record.imported_at)
        snapshot = _cache.get(key)
        if snapshot is None:
            snapshot = snapshot_from_rows(read_rows(db), record.data_source)
            _cache.clear()
            _cache[key] = snapshot
        return snapshot
    except SQLAlchemyError as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "Database atau tabel dataset belum siap"
        ) from exc
