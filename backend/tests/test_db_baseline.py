"""Tes baseline dari database: penyiapan Snapshot dari tabel dataset (db_baseline.py)
dan dependency get_baseline_snapshot (baseline.py).

PEMILIK: Orang 2 — Simulasi. Memakai dataset kecil valid_rows() dari test_data_import.py
dan SQLite in-memory (`db_session`, conftest.py); nilai harapan dihitung manual.
"""

from datetime import date

import pytest
from fastapi.testclient import TestClient
from test_data_import import PUTI_WORKBOOK, load, valid_rows, validated

from app.db.session import get_db
from app.main import app
from app.modules.data.importer import read_workbook, validate
from app.modules.evaluasi.comparison import compare
from app.modules.evaluasi.historical import historical_kpis
from app.modules.simulasi import baseline as baseline_module
from app.modules.simulasi.db_baseline import build_snapshot
from app.modules.simulasi.engine import run_simulation


@pytest.fixture(autouse=True)
def _fresh_cache():
    baseline_module._cache.clear()
    yield
    baseline_module._cache.clear()


def snapshot_of(tmp_path, session, rows):
    load(session, validated(tmp_path, rows))
    return build_snapshot(session)


def add_task(rows, task_id, status, role="ROLE-FE", resource="RES-001", **extra):
    rows["tasks"].append(
        {
            **rows["tasks"][1],
            "task_id": task_id,
            "task_name": task_id,
            "required_role_id": role,
            "status": status,
            "actual_start": date(2026, 2, 9) if status != "not_started" else None,
            **extra,
        }
    )
    rows["assignments"].append(
        {
            **rows["assignments"][1],
            "assignment_id": f"ASG-{task_id}",
            "task_id": task_id,
            "resource_id": resource,
            "role_in_task": role,
        }
    )


# ─── Penyiapan Snapshot ─────────────────────────────────────────────────────────


def test_snapshot_starts_after_last_observation(tmp_path, db_session):
    snap = snapshot_of(tmp_path, db_session, valid_rows())

    # Kejadian terakhir: WLI-0002 resolved Rabu 4 Mar 2026 → simulasi mulai Kamis.
    assert (snap.as_of, snap.start_date) == (date(2026, 3, 4), date(2026, 3, 5))
    assert snap.data_source == "synthetic"
    assert [t.task_id for t in snap.open_tasks()] == ["TSK-0002"]
    assert snap.task_by_id["TSK-0002"].planned_finish == date(2026, 2, 11)
    assert [(d.task_id, d.depends_on_task_id) for d in snap.dependencies] == [
        ("TSK-0002", "TSK-0001")
    ]
    # Assignment TSK-0001 sudah dilepas; TSK-0002 sudah ditugaskan sebelum as_of.
    assert [(a.task_id, a.resource_id, a.assigned_date) for a in snap.assignments] == [
        ("TSK-0002", "RES-002", None)
    ]
    assert snap.role_by_id["ROLE-QA"].capacity_reference == 2.5
    assert snap.role_by_id["ROLE-QA"].daily_capacity == 1.0
    assert snap.availability == ()  # cuti Februari sudah lewat
    assert len(snap.history) == 2
    assert snap.notes[0].startswith("Kondisi data per 2026-03-04")


def test_bau_share_from_open_workload_items(tmp_path, db_session):
    snap = snapshot_of(tmp_path, db_session, valid_rows())
    shares = {r.resource_id: r.bau_share for r in snap.resources}
    # Jendela 2–4 Mar = 3 hari kerja.
    # RES-001: tiket terbuka 3–4 Mar = 2 hari × 0.3 / 3.0 = 0.2 → 0.2 / 3 hari.
    # RES-002: operasional 2–4 Mar = 3 hari × 0.5 / 2.5 = 0.6 → 0.6 / 3 hari.
    assert shares == {"RES-001": pytest.approx(0.067), "RES-002": pytest.approx(0.2)}


def test_simulation_runs_on_database_snapshot(tmp_path, db_session):
    result = run_simulation(snapshot_of(tmp_path, db_session, valid_rows()))
    # RES-002 punya 1 − 0.2 = 0.8 hari-orang/hari; 3 hari-orang → Kam, Jum, Sen, Sel.
    assert result.date_of(result.tasks["TSK-0002"].finish_day) == date(2026, 3, 10)
    assert result.warnings == []


def test_status_determines_remaining_effort_and_blockers(tmp_path, db_session):
    rows = valid_rows()
    add_task(rows, "TSK-0003", "in_progress")
    add_task(rows, "TSK-0004", "in_qa")
    add_task(rows, "TSK-0005", "blocked")
    add_task(rows, "TSK-0006", "dropped")
    rows["change_events"][0].update(event_type="blocker", extension_days=1.5)
    snap = snapshot_of(tmp_path, db_session, rows)

    shares = {t.task_id: t.remaining_share for t in snap.tasks}
    assert shares == {
        "TSK-0001": 1.0,
        "TSK-0002": 1.0,
        "TSK-0003": 0.5,
        "TSK-0004": 0.2,
        "TSK-0005": 0.5,
    }
    # Rata-rata extension_days blocker 1.5 → dibulatkan ke atas 2 hari kerja.
    assert [(b.task_id, b.date_start, b.working_days) for b in snap.blocks] == [
        ("TSK-0005", snap.start_date, 2)
    ]
    assert any("dropped" in note for note in snap.notes)


def test_released_project_is_not_simulated_but_kept_in_history(tmp_path, db_session):
    rows = valid_rows()
    rows["projects"].append(
        {
            **rows["projects"][0],
            "project_id": "PRJ-002",
            "project_name": "Sudah Rilis",
            "status": "released",
            "actual_launch_date": date(2026, 3, 1),
        }
    )
    add_task(rows, "TSK-0003", "in_progress", project_id="PRJ-002")
    snap = snapshot_of(tmp_path, db_session, rows)

    assert [p.project_id for p in snap.projects] == ["PRJ-001"]
    assert "TSK-0003" not in snap.task_by_id
    assert "TSK-0003" in {r.task_id for r in snap.history}
    assert any("PRJ-002" in note for note in snap.notes)


def test_assignment_outside_known_roles_becomes_secondary_role(tmp_path, db_session):
    rows = valid_rows()
    add_task(rows, "TSK-0003", "not_started", role="ROLE-QA", resource="RES-001")
    snap = snapshot_of(tmp_path, db_session, rows)

    res = snap.resource_by_id["RES-001"]
    assert (res.secondary_role_ids, res.cross_role_capable) == (("ROLE-QA",), True)
    assert run_simulation(snap).tasks["TSK-0003"].finish_day is not None


def test_no_import_means_no_snapshot(db_session):
    assert build_snapshot(db_session) is None


# ─── Dependency API ─────────────────────────────────────────────────────────────


def test_baseline_endpoint_reads_database(tmp_path, db_session):
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        with TestClient(app) as client:
            empty = client.get("/api/v1/simulasi/baseline")
            assert empty.status_code == 503
            assert "importer" in empty.json()["detail"]

            load(db_session, validated(tmp_path, valid_rows()))
            body = client.get("/api/v1/simulasi/baseline").json()
            assert (body["data_source"], body["start_date"], body["as_of"]) == (
                "synthetic",
                "2026-03-05",
                "2026-03-04",
            )
            assert body["notes"]
            # TSK-0001: Senin–Jumat = 5 hari kerja / estimasi 4.5.
            assert client.get("/api/v1/evaluasi/historical").json()["ear"] == 1.111
    finally:
        app.dependency_overrides.clear()


def test_snapshot_is_rebuilt_after_new_import(tmp_path, db_session):
    load(db_session, validated(tmp_path, valid_rows()))
    first = baseline_module.get_baseline_snapshot(db_session)
    assert baseline_module.get_baseline_snapshot(db_session) is first  # dari cache

    rows = valid_rows()
    rows["tasks"][1]["estimated_days"] = 4.0
    load(db_session, validated(tmp_path, rows))
    assert (
        baseline_module.get_baseline_snapshot(db_session).task_by_id["TSK-0002"].estimated_days
        == 4.0
    )


# ─── Dataset PuTI lengkap ───────────────────────────────────────────────────────


@pytest.mark.skipif(not PUTI_WORKBOOK.is_file(), reason="puti_datasets.xlsx tidak ada di root repo")
def test_puti_workbook_simulates_end_to_end(db_session):
    dataset = validate(read_workbook(PUTI_WORKBOOK))
    load(db_session, dataset)
    snap = build_snapshot(db_session)

    result = run_simulation(snap)
    assert result.warnings == []
    assert all(o.finish_day is not None for o in result.tasks.values())

    response = compare(snap, [], replications=3, seed=1)
    values = {k.key: k.value for k in response.baseline.kpis}
    assert all(v is not None for v in values.values()), values
    assert len(response.baseline.projects) == len(snap.projects)

    history = historical_kpis(snap)
    assert history.ear is not None and history.rework_rate is not None
