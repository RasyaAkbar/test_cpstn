"""Tes Iterasi 2: KPI (FR-04.1 s.d. FR-04.10) dan perbandingan baseline vs skenario.

PEMILIK: Orang 3 — KPI. Nilai harapan dihitung manual dari make_snapshot():
T1 = 3 hari, R1 = 1 hari-orang/hari, target launch Rabu 4 Nov 2026 (hari ke-0 = Senin
2 Nov), capacity_reference role = 3.0.
"""

from datetime import date

import pytest
from conftest import make_snapshot

from app.modules.evaluasi.comparison import (
    compare,
    kpi_status,
    percentile,
    rank_scenarios,
)
from app.modules.evaluasi.historical import historical_kpis
from app.modules.evaluasi.kpi import KPI_DEFINITIONS, compute_kpis, sustained_overload
from app.modules.evaluasi.schemas import Evaluation, KpiValue
from app.modules.simulasi.domain import (
    Assignment,
    Dependency,
    Holiday,
    Resource,
    Task,
    TaskRecord,
)
from app.modules.simulasi.engine import run_simulation
from app.modules.simulasi.rules import apply_scenario
from app.modules.simulasi.schemas import MemberAbsenceParams, Scenario
from app.modules.simulasi.synthetic_data import build_synthetic_snapshot

ABSENCE = MemberAbsenceParams(
    resource_id="R1", date_start=date(2026, 11, 2), date_end=date(2026, 11, 3)
)


def _scenario(sid: str, params) -> Scenario:
    now = "2026-11-03T00:00:00Z"
    return Scenario(
        scenario_id=sid,
        name=sid,
        data_source="test",
        created_at=now,
        updated_at=now,
        parameters=params,
    )


def _kpis(snapshot):
    return compute_kpis(run_simulation(snapshot))


# ─── FR-04.1 Schedule Variance ──────────────────────────────────────────────────


def test_baseline_on_target_has_zero_schedule_variance(tiny_snapshot):
    run = _kpis(tiny_snapshot)
    assert (run.projects[0].sv_days, run.projects[0].on_target) == (0, True)
    assert run.values["projects_late"] == 0
    assert run.values["sv_total_days"] == 0


def test_absence_schedule_variance_in_working_days(tiny_snapshot):
    run = _kpis(apply_scenario(tiny_snapshot, ABSENCE))
    assert run.projects[0].projected_finish == date(2026, 11, 6)  # Rabu, Kamis, Jumat
    assert run.projects[0].sv_days == 2  # Kamis dan Jumat setelah target Rabu
    assert run.values["projects_late"] == 1
    assert (run.values["sv_total_days"], run.values["sv_max_days"]) == (2, 2)


def test_schedule_variance_skips_weekend_and_can_be_negative():
    late = make_snapshot(tasks=(Task("T1", "P1", "A", "DEV", "MED", 1, 7.0),))
    # 7 hari kerja: selesai Selasa 10 Nov; hari kerja setelah Rabu 4 Nov = Kam, Jum, Sen, Sel.
    assert _kpis(late).projects[0].sv_days == 4

    early = make_snapshot(tasks=(Task("T1", "P1", "A", "DEV", "MED", 1, 1.0),))
    run = _kpis(early)  # selesai Senin, target Rabu
    assert (run.projects[0].sv_days, run.values["sv_max_days"]) == (-2, -2)
    assert run.values["sv_total_days"] == 0


# ─── FR-04.3 s.d. FR-04.6: RLI, overload, WBI, SOI ──────────────────────────────


def _started_backlog(count: int):
    """R1 memegang `count` task in_progress 4 hari; dikerjakan berurutan."""
    tasks = tuple(
        Task(f"T{i}", "P1", f"Task {i}", "DEV", "MED", i, 4.0, status="in_progress")
        for i in range(1, count + 1)
    )
    return make_snapshot(
        tasks=tasks,
        assignments=tuple(Assignment(t.task_id, "R1") for t in tasks),
        resources=(Resource("R1", "Dev Satu", "DEV"),),
    )


def test_rli_counts_started_tasks_until_they_finish():
    run = _kpis(_started_backlog(5))
    r1 = run.members[0]
    # Selesai hari 3, 9, 15, 21, 25 → task aktif per minggu 5, 4, 3, 2 (dibagi 3.0).
    assert r1.weekly_rli == [1.667, 1.333, 1.0, 0.667]
    assert run.values["rli_peak"] == 1.667
    # Threshold 1.0: minggu ke-0 dan ke-1 overload (1.0 tepat di threshold tidak).
    assert r1.overload_weeks == 2
    # SOI = 2 minggu × rata-rata kelebihan (0.667 + 0.333) / 2.
    assert r1.soi == pytest.approx(1.0)
    assert run.values["sustained_overload_resources"] == 1


def test_overload_threshold_is_configurable():
    run = compute_kpis(run_simulation(_started_backlog(5)), threshold=1.5)
    assert run.values["overload_resource_weeks"] == 1
    assert run.values["soi_max"] == 0  # satu minggu saja bukan overload berkelanjutan


def test_sustained_overload_takes_heaviest_episode():
    series = [1.5, 1.5, 0.5, 2.0, 2.0, 2.0, None, 3.0]
    assert sustained_overload(series, 1.0) == pytest.approx(3.0)  # 3 minggu × 1.0


def test_bau_share_adds_to_rli_and_reduces_capacity():
    busy = Resource("R1", "Dev Satu", "DEV", bau_share=0.25)
    snap = make_snapshot(resources=(busy, Resource("R2", "Dev Dua", "DEV")))
    result = run_simulation(snap)
    assert result.resources["R1"].capacity[0] == 0.75
    assert result.tasks["T1"].finish_day == 3  # 3 / 0.75 = 4 hari kerja
    assert compute_kpis(result).members[0].weekly_rli == [round(1 / 3 + 0.25, 3)]


def test_workload_balance_index():
    even = make_snapshot(
        tasks=(
            Task("T1", "P1", "A", "DEV", "MED", 1, 3.0),
            Task("T2", "P1", "B", "DEV", "MED", 1, 3.0),
        ),
        assignments=(Assignment("T1", "R1"), Assignment("T2", "R2")),
    )
    assert _kpis(even).values["wbi"] == 1.0
    # R1 1/3, R2 0 → CV = 1 → WBI = 0.
    assert _kpis(make_snapshot()).values["wbi"] == 0.0


# ─── FR-04.7 Cascade Delay Impact ───────────────────────────────────────────────


def test_cascade_delay_impact_propagates_by_dependency_type():
    snap = make_snapshot(
        tasks=(
            Task("T1", "P1", "A", "DEV", "MED", 1, 3.0, planned_finish=date(2026, 11, 2)),
            Task("T2", "P1", "B", "DEV", "MED", 2, 1.0),
            Task("T3", "P1", "C", "DEV", "MED", 3, 1.0),
        ),
        assignments=(Assignment("T1", "R1"), Assignment("T2", "R2"), Assignment("T3", "R2")),
        dependencies=(
            Dependency("T2", "T1", "hard", 1.0),
            Dependency("T3", "T2", "soft", 0.3),
            Dependency("T3", "T1", "soft", 0.3),
        ),
    )
    run = _kpis(snap)
    # T1 rencana selesai Senin, simulasi Rabu → terlambat 2 hari kerja. T2 menerima 2 × 1.0;
    # T3 menerima 2 × 0.3 (jalur terkuat: T1→T2→T3 = 1.0 × 0.3 = T1→T3 = 0.3).
    assert [(c.task_id, c.delay_days, c.downstream_tasks, c.cdi) for c in run.cascade] == [
        ("T1", 2, 2, 2.6)
    ]
    assert run.values["cdi_max"] == 2.6


# ─── FR-04.10 Blocked dan Reallocated Time Ratio ────────────────────────────────


def _waiting_snapshot(with_independent_task: bool):
    tasks = [
        Task("T1", "P1", "A", "DEV", "MED", 1, 2.0),
        Task("T2", "P1", "B", "DEV", "MED", 2, 2.0),
    ]
    assignments = [Assignment("T1", "R1"), Assignment("T2", "R2")]
    if with_independent_task:
        tasks.append(Task("T3", "P1", "C", "DEV", "MED", 3, 1.0))
        assignments.append(Assignment("T3", "R2"))
    return make_snapshot(
        tasks=tuple(tasks),
        assignments=tuple(assignments),
        dependencies=(Dependency("T2", "T1"),),
    )


def test_blocked_ratio_without_replacement_work():
    run = _kpis(_waiting_snapshot(False))
    # R2 menunggu Senin–Selasa tanpa pekerjaan lain: 2 dari 8 hari-orang (2 anggota × 4 hari).
    assert run.values["blocked_ratio"] == 25.0
    assert run.values["reallocated_ratio"] == 0.0


def test_reallocated_ratio_when_independent_task_fills_waiting_time():
    run = _kpis(_waiting_snapshot(True))
    # Senin R2 mengerjakan T3 selama menunggu T1; Selasa menganggur.
    assert run.values["blocked_ratio"] == 12.5
    assert run.values["reallocated_ratio"] == 50.0
    r2 = next(m for m in run.members if m.resource_id == "R2")
    assert (r2.blocked_ratio, r2.reallocated_ratio) == (25.0, 50.0)


def test_every_kpi_is_defined_and_computed(tiny_snapshot):
    values = _kpis(tiny_snapshot).values
    assert set(values) == {k.key for k in KPI_DEFINITIONS}
    assert all(k.fr.startswith("FR-04.") for k in KPI_DEFINITIONS)


# ─── FR-04.8 EAR dan FR-04.9 Rework Rate (data historis) ────────────────────────


def _record(task_id, role, status, start=None, finish=None, estimate=2.0, rejects=0):
    return TaskRecord(
        task_id, "P1", "Proyek Uji", role, "MED", estimate, status, start, finish, rejects
    )


def test_historical_estimate_accuracy_and_rework_rate():
    snap = make_snapshot(
        holidays=(Holiday(date(2026, 11, 3), "Libur uji"),),
        history=(
            # Senin–Rabu dengan libur Selasa = 2 hari kerja / estimasi 2 → 1.0
            _record("H1", "DEV", "done", date(2026, 11, 2), date(2026, 11, 4), rejects=1),
            # Rabu–Jumat = 3 hari kerja / estimasi 6 → 0.5
            _record("H2", "QA", "done", date(2026, 11, 4), date(2026, 11, 6), estimate=6.0),
            _record("H3", "DEV", "in_qa"),
            _record("H4", "DEV", "in_progress", rejects=2),  # pernah ditolak QA
            _record("H5", "DEV", "not_started"),  # belum masuk QA
        ),
    )
    h = historical_kpis(snap)
    assert h.ear == pytest.approx(5 / 8, abs=1e-3)
    assert {g.key: g.value for g in h.ear_by_role} == {"DEV": 1.0, "QA": 0.5}
    assert h.rework_rate == pytest.approx(50.0)  # H1 dan H4 dari H1, H2, H3, H4
    assert {g.key: (g.value, g.tasks) for g in h.rework_by_role} == {
        "DEV": (pytest.approx(66.667), 3),
        "QA": (0.0, 1),
    }


def test_historical_without_history_is_empty(tiny_snapshot):
    h = historical_kpis(tiny_snapshot)
    assert (h.ear, h.rework_rate, h.ear_by_role) == (None, None, [])


# ─── KPI Comparator ─────────────────────────────────────────────────────────────


def test_percentile_interpolates():
    assert percentile([1, 2, 3, 4], 0.5) == 2.5
    assert percentile([5], 0.9) == 5


def test_status_follows_kpi_direction():
    assert kpi_status("sv_total_days", 3) == "worse"
    assert kpi_status("sv_total_days", -1) == "better"
    assert kpi_status("sv_total_days", 0) == "same"
    assert kpi_status("wbi", 0.2) == "better"


def test_compare_marks_absence_worse_than_baseline(tiny_snapshot):
    response = compare(tiny_snapshot, [_scenario("S1", ABSENCE)], replications=0, seed=1)
    assert all(k.delta is None for k in response.baseline.kpis)
    sv = next(k for k in response.scenarios[0].kpis if k.key == "sv_total_days")
    assert (sv.value, sv.delta, sv.status) == (2, 2, "worse")
    probability = next(k for k in response.scenarios[0].kpis if k.key == "on_time_probability")
    assert probability.value is None  # tanpa replikasi
    assert response.best_scenario_id == "S1"


def test_cover_scenario_ranks_above_plain_absence(tiny_snapshot):
    covered = ABSENCE.model_copy(update={"auto_cover": True})
    response = compare(tiny_snapshot, [_scenario("S1", ABSENCE), _scenario("S2", covered)], 0, 1)
    assert response.ranking == ["S2", "S1"]
    assert response.best_scenario_id == "S2"


def _evaluation(sid, **values):
    kpis = [KpiValue(key=k.key, value=values.get(k.key, 0)) for k in KPI_DEFINITIONS]
    return Evaluation(
        scenario_id=sid,
        name=sid,
        kpis=kpis,
        projects=[],
        members=[],
        cascade=[],
        week_starts=[],
        warnings=[],
    )


def test_ranking_uses_late_projects_before_variance():
    a = _evaluation("A", projects_late=1, sv_total_days=1)
    b = _evaluation("B", projects_late=0, sv_total_days=30)
    assert rank_scenarios([a, b]) == ["B", "A"]


def test_ranking_prefers_higher_balance_index_on_tie():
    assert rank_scenarios([_evaluation("A", wbi=0.4), _evaluation("B", wbi=0.9)]) == ["B", "A"]


def test_replications_give_ordered_distribution_and_probability():
    baseline = build_synthetic_snapshot()
    response = compare(baseline, [], replications=30, seed=3)
    for kpi in response.baseline.kpis:
        d = kpi.distribution
        if kpi.key in ("on_time_probability", "cdi_max", "reallocated_ratio"):
            continue  # dihitung lintas replikasi / hanya run deterministik / bisa kosong
        assert d is not None and d.p10 <= d.median <= d.p90, kpi.key
    probability = next(k for k in response.baseline.kpis if k.key == "on_time_probability")
    assert 0 <= probability.value <= 100
    for project in response.baseline.projects:
        assert 0 <= project.on_target_probability <= 1


def test_on_time_probability_matches_replication_share(tiny_snapshot):
    response = compare(tiny_snapshot, [], replications=200, seed=11)
    project = response.baseline.projects[0]
    value = next(k.value for k in response.baseline.kpis if k.key == "on_time_probability")
    assert value == pytest.approx(project.on_target_probability * 100, abs=0.1)
    # Effort segitiga(2, 6, modus 3); tepat waktu jika effort ≤ 3: P = 1/4.
    assert project.on_target_probability == pytest.approx(0.25, abs=0.08)


def test_common_random_numbers_cancel_out_for_identical_snapshot():
    """Skenario tanpa perubahan efektif harus identik dengan baseline di setiap replikasi."""
    baseline = build_synthetic_snapshot()
    noop = MemberAbsenceParams(
        resource_id="RES-06", date_start=date(2026, 12, 21), date_end=date(2026, 12, 31)
    )  # sama dengan cuti di baseline
    response = compare(baseline, [_scenario("S1", noop)], replications=10, seed=5)
    for base_kpi, scen_kpi in zip(response.baseline.kpis, response.scenarios[0].kpis, strict=True):
        assert scen_kpi.distribution == base_kpi.distribution
        assert scen_kpi.status in ("same", None)


# ─── API evaluasi ───────────────────────────────────────────────────────────────


def test_kpi_definitions_endpoint(api):
    body = api.get("/api/v1/evaluasi/kpi-definitions").json()
    assert [k["key"] for k in body] == [k.key for k in KPI_DEFINITIONS]
    assert body[0]["fr"] == "FR-04.1"


def test_compare_endpoint(api):
    payload = {"name": "Absen", "parameters": ABSENCE.model_dump(mode="json")}
    sid = api.post("/api/v1/simulasi/scenarios", json=payload).json()["scenario_id"]
    body = api.post(
        "/api/v1/evaluasi/compare",
        json={"scenario_ids": [sid, sid], "replications": 5, "overload_threshold": 0.5},
    ).json()
    assert len(body["scenarios"]) == 1  # duplikat dibuang
    assert body["best_scenario_id"] == sid
    assert body["overload_threshold"] == 0.5
    assert body["scenarios"][0]["kpis"][0]["distribution"] is not None
    member = body["baseline"]["members"][0]
    assert len(member["weekly_rli"]) == len(body["baseline"]["week_starts"])


def test_compare_defaults_to_100_replications(api):
    payload = {"name": "Absen", "parameters": ABSENCE.model_dump(mode="json")}
    sid = api.post("/api/v1/simulasi/scenarios", json=payload).json()["scenario_id"]
    body = api.post("/api/v1/evaluasi/compare", json={"scenario_ids": [sid]}).json()
    assert body["replications"] == 100


@pytest.mark.parametrize(
    "payload",
    [
        {"scenario_ids": []},
        {"scenario_ids": ["S"], "replications": 5000},
        {"scenario_ids": ["S"], "overload_threshold": 0},
    ],
)
def test_compare_validates_request(api, payload):
    assert api.post("/api/v1/evaluasi/compare", json=payload).status_code == 422


def test_compare_unknown_scenario_returns_404(api):
    response = api.post("/api/v1/evaluasi/compare", json={"scenario_ids": ["SCN-999"]})
    assert response.status_code == 404


def test_historical_endpoint(api):
    body = api.get("/api/v1/evaluasi/historical").json()
    assert body["data_source"] == "test"
    assert (body["ear"], body["rework_rate"]) == (None, None)
