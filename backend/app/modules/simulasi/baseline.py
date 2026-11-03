"""Sumber baseline untuk simulasi (langkah 1 desain IV.2.3).

PEMILIK: Orang 2 — Simulasi (Iterasi 1).

Satu-satunya titik masuk baseline. Saat modul Data / Digital Twin sudah menyediakan
data PuTI, ubah fungsi ini untuk membangun Snapshot dari data tersebut (dengan
data_source="puti"); modul lain tidak perlu diubah.
"""

from functools import lru_cache

from app.modules.simulasi.domain import Snapshot
from app.modules.simulasi.synthetic_data import build_synthetic_snapshot


@lru_cache
def get_baseline_snapshot() -> Snapshot:
    """Dependency FastAPI. Snapshot frozen sehingga aman dipakai bersama antar request."""
    return build_synthetic_snapshot()
