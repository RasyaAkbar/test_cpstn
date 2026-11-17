"""Fixture bersama tes simulasi (Orang 2) dan evaluasi (Orang 3).

PEMILIK: Orang 2 — Simulasi (kontrak data Snapshot). Orang 3 memakai fixture yang sama.

`tiny_snapshot` membuat baseline kecil yang hasilnya bisa dihitung manual (validasi
"independently calculated examples", III.3.3): satu proyek, satu role berkapasitas
1.0 hari-orang/hari, awal Senin 2 November 2026.
"""

from dataclasses import replace
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.main import app
from app.modules.simulasi.baseline import get_baseline_snapshot
from app.modules.simulasi.domain import (
    Assignment,
    ComplexityLevel,
    Project,
    Resource,
    Role,
    Snapshot,
    Task,
)
from app.modules.simulasi.store import ScenarioStore, get_scenario_store

MONDAY = date(2026, 11, 2)


def make_snapshot(**overrides) -> Snapshot:
    """T1 (3 hari) dikerjakan R1; target launch Rabu 4 Nov 2026."""
    base = Snapshot(
        start_date=MONDAY,
        data_source="test",
        projects=(Project("P1", "Proyek Uji", 1, MONDAY, date(2026, 11, 4)),),
        roles=(Role("DEV", "Developer", 1.0), Role("QA", "Quality Assurance", 1.0)),
        resources=(
            Resource("R1", "Dev Satu", "DEV"),
            Resource("R2", "Dev Dua", "DEV"),
        ),
        complexity_levels=(ComplexityLevel("MED", "Sedang", 2, 6, 1.5),),
        tasks=(Task("T1", "P1", "Tugas satu", "DEV", "MED", 1, 3.0),),
        assignments=(Assignment("T1", "R1"),),
    )
    return replace(base, **overrides)


@pytest.fixture
def tiny_snapshot() -> Snapshot:
    return make_snapshot()


@pytest.fixture
def db_session():
    """SQLite in-memory dengan tabel dataset dan foreign key aktif (tes modul Data)."""
    engine = create_engine(
        "sqlite+pysqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(connection, _record):
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


@pytest.fixture
def api():
    """Klien API dengan baseline kecil dan store skenario baru per tes."""
    store = ScenarioStore()
    app.dependency_overrides[get_baseline_snapshot] = lambda: make_snapshot()
    app.dependency_overrides[get_scenario_store] = lambda: store
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()
