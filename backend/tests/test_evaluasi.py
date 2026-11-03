"""Tes Iterasi 2: KPI dan perbandingan baseline vs skenario.

PEMILIK: Orang 3 — KPI. Nilai harapan dihitung manual dari make_snapshot():
T1 = 3 hari, R1 = 1 hari-orang/hari, target launch Rabu 4 Nov 2026 (hari ke-2).
"""

from datetime import date

import pytest

from app.modules.evaluasi.comparison import (
    compare,
    kpi_status,
    percentile,
    rank_scenarios,
)
from app.modules.evaluasi.kpi import KPI_DEFINITIONS, compute_kpis
from app.modules.evaluasi.schemas import Evaluation, KpiValue
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


# ─── KPI Calculator ─────────────────────────────────────────────────────────────


def test_baseline_kpis_hand_calculated(tiny_snapshot):
    result = run_simulation(tiny_snapshot)
    run = compute_kpis(result, result)
    assert run.values["projects_missing_target"] == 0
    assert run.values["total_delay_days"] == 0
    assert run.values["completion_span_days"] == 2
    assert run.values["tasks_delayed_by_dependency"] == 0
    r1 = next(m for m in run.members if m.resource_id == "R1")
    # Beban 3 hari-orang, kapasitas Senin–Rabu = 3 → 100%, belum overload.
    assert (r1.demand_days, r1.capacity_days, r1.load_pct, r1.overloaded) == (3, 3, 100, False)


def test_absence_kpis_hand_calculated(tiny_snapshot):
    base = run_simulation(tiny_snapshot)
    scen = run_simulation(apply_scenario(tiny_snapshot, ABSENCE))
    run = compute_kpis(scen, base)
    assert run.projects[0].projected_finish == date(2026, 11, 6)  # Rabu, Kamis, Jumat
    assert run.values["projects_missing_target"] == 1
    assert run.values["total_delay_days"] == 2
    assert run.values["tasks_dropped_or_deferred"] == 1
    # Kapasitas sampai target hanya Rabu = 1 hari-orang, beban 3 → 300%.
    assert run.values["max_member_load_pct"] == 300
    assert run.values["overloaded_members"] == 1


def test_every_kpi_is_defined_and_computed(tiny_snapshot):
    result = run_simulation(tiny_snapshot)
    assert set(compute_kpis(result, result).values) == {k.key for k in KPI_DEFINITIONS}


# ─── KPI Comparator ─────────────────────────────────────────────────────────────


def test_percentile_interpolates():
    assert percentile([1, 2, 3, 4], 0.5) == 2.5
    assert percentile([5], 0.9) == 5


def test_status_follows_kpi_direction():
    assert kpi_status("total_delay_days", 3) == "worse"
    assert kpi_status("total_delay_days", -1) == "better"
    assert kpi_status("total_delay_days", 0) == "same"


def test_compare_marks_absence_worse_than_baseline(tiny_snapshot):
    response = compare(tiny_snapshot, [_scenario("S1", ABSENCE)], replications=0, seed=1)
    assert all(k.delta is None for k in response.baseline.kpis)
    delay = next(k for k in response.scenarios[0].kpis if k.key == "total_delay_days")
    assert (delay.value, delay.delta, delay.status) == (2, 2, "worse")
    assert response.best_scenario_id == "S1"


def test_cover_scenario_ranks_above_plain_absence(tiny_snapshot):
    covered = ABSENCE.model_copy(update={"auto_cover": True})
    response = compare(tiny_snapshot, [_scenario("S1", ABSENCE), _scenario("S2", covered)], 0, 1)
    assert response.ranking == ["S2", "S1"]
    assert response.best_scenario_id == "S2"


def test_ranking_uses_target_before_delay():
    def evaluation(sid, missing, delay):
        kpis = [KpiValue(key=k.key, value=0) for k in KPI_DEFINITIONS]
        for k in kpis:
            k.value = {"projects_missing_target": missing, "total_delay_days": delay}.get(k.key, 0)
        return Evaluation(
            scenario_id=sid, name=sid, kpis=kpis, projects=[], members=[], warnings=[]
        )

    assert rank_scenarios([evaluation("A", 1, 1), evaluation("B", 0, 30)]) == ["B", "A"]


def test_replications_give_ordered_distribution_and_probability():
    baseline = build_synthetic_snapshot()
    response = compare(baseline, [], replications=30, seed=3)
    for kpi in response.baseline.kpis:
        d = kpi.distribution
        assert d is not None and d.p10 <= d.median <= d.p90
    for project in response.baseline.projects:
        assert 0 <= project.on_target_probability <= 1


def test_common_random_numbers_cancel_out_for_identical_snapshot():
    """Skenario tanpa perubahan efektif harus identik dengan baseline di setiap replikasi."""
    baseline = build_synthetic_snapshot()
    noop = MemberAbsenceParams(
        resource_id="RES-06", date_start=date(2026, 12, 21), date_end=date(2026, 12, 31)
    )  # sama dengan cuti di baseline
    response = compare(baseline, [_scenario("S1", noop)], replications=10, seed=5)
    for base_kpi, scen_kpi in zip(response.baseline.kpis, response.scenarios[0].kpis, strict=True):
        assert scen_kpi.distribution == base_kpi.distribution
        assert scen_kpi.status == "same"


# ─── API evaluasi ───────────────────────────────────────────────────────────────


def test_kpi_definitions_endpoint(api):
    body = api.get("/api/v1/evaluasi/kpi-definitions").json()
    assert [k["key"] for k in body] == [k.key for k in KPI_DEFINITIONS]


def test_compare_endpoint(api):
    payload = {"name": "Absen", "parameters": ABSENCE.model_dump(mode="json")}
    sid = api.post("/api/v1/simulasi/scenarios", json=payload).json()["scenario_id"]
    body = api.post(
        "/api/v1/evaluasi/compare", json={"scenario_ids": [sid, sid], "replications": 5}
    ).json()
    assert len(body["scenarios"]) == 1  # duplikat dibuang
    assert body["best_scenario_id"] == sid
    assert body["scenarios"][0]["kpis"][0]["distribution"] is not None


@pytest.mark.parametrize(
    "payload", [{"scenario_ids": []}, {"scenario_ids": ["S"], "replications": 5000}]
)
def test_compare_validates_request(api, payload):
    assert api.post("/api/v1/evaluasi/compare", json=payload).status_code == 422


def test_compare_unknown_scenario_returns_404(api):
    response = api.post("/api/v1/evaluasi/compare", json={"scenario_ids": ["SCN-999"]})
    assert response.status_code == 404
