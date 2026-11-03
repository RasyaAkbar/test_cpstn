"""Tes Iterasi 1: scenario setup dan what-if simulation.

PEMILIK: Orang 2 — Simulasi. Nilai harapan dihitung manual dari make_snapshot()
(1 hari-orang/hari, awal Senin 2 Nov 2026 = hari ke-0).
"""

from dataclasses import replace
from datetime import date

import pytest
from conftest import make_snapshot

from app.modules.simulasi.domain import (
    Assignment,
    Availability,
    Dependency,
    Holiday,
    Resource,
    Task,
)
from app.modules.simulasi.engine import run_replications, run_simulation
from app.modules.simulasi.rules import ScenarioError, apply_scenario
from app.modules.simulasi.schemas import (
    CriticalBugParams,
    MemberAbsenceParams,
    NewMemberParams,
    RotationParams,
    TaskBlockerParams,
    TaskOverrunParams,
)
from app.modules.simulasi.synthetic_data import build_synthetic_snapshot

# ─── Mesin simulasi: contoh yang dihitung manual ────────────────────────────────


def test_task_of_three_days_finishes_on_wednesday(tiny_snapshot):
    result = run_simulation(tiny_snapshot)
    assert (result.tasks["T1"].start_day, result.tasks["T1"].finish_day) == (0, 2)


def test_holiday_and_weekend_are_not_working_days():
    holiday = make_snapshot(holidays=(Holiday(date(2026, 11, 3), "Libur uji"),))
    assert run_simulation(holiday).tasks["T1"].finish_day == 3  # Senin, Rabu, Kamis

    long_task = make_snapshot(tasks=(Task("T1", "P1", "Panjang", "DEV", "MED", 1, 6.0),))
    assert run_simulation(long_task).tasks["T1"].finish_day == 7  # Sen–Jum + Senin depan


def test_full_dependency_waits_for_predecessor_to_finish():
    snap = make_snapshot(
        tasks=(
            Task("T1", "P1", "A", "DEV", "MED", 1, 2.0),
            Task("T2", "P1", "B", "DEV", "MED", 2, 2.0),
        ),
        assignments=(Assignment("T1", "R1"), Assignment("T2", "R2")),
        dependencies=(Dependency("T2", "T1", propagation_factor=1.0),),
    )
    result = run_simulation(snap)
    assert result.tasks["T2"].dependency_ready_day == 2
    assert result.tasks["T2"].finish_day == 3
    assert sum(result.resources["R2"].idle_waiting) == pytest.approx(2.0)  # R2 menunggu 2 hari


def test_partial_propagation_factor_allows_early_start():
    snap = make_snapshot(
        tasks=(
            Task("T1", "P1", "A", "DEV", "MED", 1, 2.0),
            Task("T2", "P1", "B", "DEV", "MED", 2, 2.0),
        ),
        assignments=(Assignment("T1", "R1"), Assignment("T2", "R2")),
        dependencies=(Dependency("T2", "T1", propagation_factor=0.5),),
    )
    assert run_simulation(snap).tasks["T2"].start_day == 1  # T1 sudah 50% di akhir hari 0


def test_higher_priority_project_is_worked_first():
    snap = make_snapshot(
        projects=(
            replace(make_snapshot().projects[0], priority_rank=2),
            replace(make_snapshot().projects[0], project_id="P2", priority_rank=1),
        ),
        tasks=(
            Task("T1", "P1", "A", "DEV", "MED", 1, 2.0),
            Task("T2", "P2", "B", "DEV", "MED", 1, 2.0),
        ),
        assignments=(Assignment("T1", "R1"), Assignment("T2", "R1")),
    )
    result = run_simulation(snap)
    assert result.tasks["T2"].finish_day == 1
    assert result.tasks["T1"].finish_day == 3


def test_onboarding_ramp_up():
    newcomer = Resource(
        "R1", "Baru", "DEV", join_date=date(2026, 11, 2), onboarding_days=2, initial_capacity=0.5
    )
    result = run_simulation(make_snapshot(resources=(newcomer,)))
    assert result.resources["R1"].capacity[:3] == [0.5, 0.75, 1.0]
    assert result.tasks["T1"].finish_day == 3  # 0.5 + 0.75 + 1.0 + 0.75


def test_cross_role_member_works_slower():
    cross = Resource("R1", "Lintas", "QA", ("DEV",), cross_role_capable=True)
    assert run_simulation(make_snapshot(resources=(cross,))).tasks["T1"].finish_day == 3  # 3/0.75


def test_unqualified_assignee_is_reported():
    qa_only = Resource("R1", "QA", "QA")
    result = run_simulation(make_snapshot(resources=(qa_only,)))
    assert result.tasks["T1"].finish_day is None
    assert any("tidak punya role" in w for w in result.warnings)


def test_replications_are_reproducible_and_within_complexity_range(tiny_snapshot):
    first = run_replications(tiny_snapshot, 20, seed=7)
    second = run_replications(tiny_snapshot, 20, seed=7)
    efforts = [r.tasks["T1"].effort_days for r in first]
    assert efforts == [r.tasks["T1"].effort_days for r in second]
    assert all(2 <= e <= 6 for e in efforts)
    assert len(set(efforts)) > 1


def test_synthetic_baseline_runs_without_warnings():
    result = run_simulation(build_synthetic_snapshot())
    assert result.warnings == []
    assert all(o.finish_day is not None for o in result.tasks.values())


# ─── Aturan skenario (Tabel 4.2) ────────────────────────────────────────────────


def test_scenario_never_mutates_baseline(tiny_snapshot):
    params = TaskOverrunParams(task_id="T1", revised_estimated_days=5)
    changed = apply_scenario(tiny_snapshot, params)
    assert tiny_snapshot.task_by_id["T1"].estimated_days == 3
    assert run_simulation(changed).tasks["T1"].finish_day == 4


def test_absence_delays_and_auto_cover_recovers(tiny_snapshot):
    absence = MemberAbsenceParams(
        resource_id="R1", date_start=date(2026, 11, 2), date_end=date(2026, 11, 3)
    )
    assert run_simulation(apply_scenario(tiny_snapshot, absence)).tasks["T1"].finish_day == 4

    covered = absence.model_copy(update={"auto_cover": True})
    snap = apply_scenario(tiny_snapshot, covered)
    assert ("T1", "R2") in {(a.task_id, a.resource_id) for a in snap.assignments}
    assert run_simulation(snap).tasks["T1"].finish_day == 2


def test_blocker_holds_task_for_working_days(tiny_snapshot):
    params = TaskBlockerParams(task_id="T1", block_start=date(2026, 11, 2), block_days=2)
    result = run_simulation(apply_scenario(tiny_snapshot, params))
    assert result.tasks["T1"].finish_day == 4
    assert sum(result.resources["R1"].idle_waiting) == pytest.approx(2.0)


def test_critical_bug_pre_empts_feature_work(tiny_snapshot):
    params = CriticalBugParams(resource_id="R1", report_date=date(2026, 11, 2), fix_days=1)
    result = run_simulation(apply_scenario(tiny_snapshot, params))
    assert result.resources["R1"].used_workload[0] == pytest.approx(1.0)
    assert result.tasks["T1"].finish_day == 3


def test_new_member_with_mentor_overhead(tiny_snapshot):
    params = NewMemberParams(
        resource_name="Baru",
        role_id="DEV",
        join_date=date(2026, 11, 2),
        onboarding_days=2,
        initial_capacity=0.5,
        mentor_resource_id="R1",
        mentor_overhead=0.2,
        project_id="P1",
    )
    snap = apply_scenario(tiny_snapshot, params)
    result = run_simulation(snap)
    assert result.resources["R1"].capacity[:3] == [0.8, 0.8, 1.0]
    # Hari 0: 0.8 + 0.5, hari 1: 0.8 + 0.75 → 2.85 hari-orang; selesai hari 2.
    assert result.tasks["T1"].finish_day == 2


def test_withdrawal_hands_tasks_to_same_role_member(tiny_snapshot):
    params = RotationParams(resource_id="R1", transfer_date=date(2026, 11, 3), from_project_id="P1")
    snap = apply_scenario(tiny_snapshot, params)
    assert snap.resource_by_id["R1"].leave_date == date(2026, 11, 3)
    result = run_simulation(snap)
    assert result.tasks["T1"].spent_by_resource == pytest.approx({"R1": 1.0, "R2": 2.0})


def test_invalid_reference_raises(tiny_snapshot):
    with pytest.raises(ScenarioError):
        apply_scenario(tiny_snapshot, TaskOverrunParams(task_id="X", revised_estimated_days=2))
    with pytest.raises(ScenarioError):
        absent = MemberAbsenceParams(
            resource_id="R1", date_start=date(2026, 1, 1), date_end=date(2026, 1, 2)
        )
        apply_scenario(tiny_snapshot, absent)


def test_absence_dates_are_ordered():
    with pytest.raises(ValueError):
        MemberAbsenceParams(
            resource_id="R1", date_start=date(2026, 11, 5), date_end=date(2026, 11, 4)
        )


def test_availability_from_baseline_is_respected():
    snap = make_snapshot(availability=(Availability("R1", date(2026, 11, 2), date(2026, 11, 2)),))
    assert run_simulation(snap).tasks["T1"].finish_day == 3


# ─── API scenario setup (UC-01 s.d. UC-04) ──────────────────────────────────────

OVERRUN = {
    "name": "Overrun T1",
    "parameters": {"situation": "task_overrun", "task_id": "T1", "revised_estimated_days": 5},
}


def test_scenario_crud_and_duplicate(api):
    created = api.post("/api/v1/simulasi/scenarios", json=OVERRUN)
    assert created.status_code == 201
    sid = created.json()["scenario_id"]
    assert created.json()["data_source"] == "test"

    copy = api.post(f"/api/v1/simulasi/scenarios/{sid}/duplicate").json()
    assert copy["name"] == "Overrun T1 (salinan)"
    assert copy["parameters"] == created.json()["parameters"]

    edited = {**OVERRUN, "parameters": {**OVERRUN["parameters"], "revised_estimated_days": 8}}
    assert api.put(f"/api/v1/simulasi/scenarios/{sid}", json=edited).status_code == 200
    assert (
        api.get(f"/api/v1/simulasi/scenarios/{sid}").json()["parameters"]["revised_estimated_days"]
        == 8
    )

    assert len(api.get("/api/v1/simulasi/scenarios").json()) == 2
    assert api.delete(f"/api/v1/simulasi/scenarios/{sid}").status_code == 204
    assert api.get(f"/api/v1/simulasi/scenarios/{sid}").status_code == 404


def test_scenario_with_unknown_task_is_rejected(api):
    bad = {**OVERRUN, "parameters": {**OVERRUN["parameters"], "task_id": "NOPE"}}
    response = api.post("/api/v1/simulasi/scenarios", json=bad)
    assert response.status_code == 422
    assert response.json()["detail"] == "Task NOPE tidak ada di baseline"


def test_unknown_situation_is_rejected(api):
    response = api.post(
        "/api/v1/simulasi/scenarios", json={"name": "x", "parameters": {"situation": "meteor"}}
    )
    assert response.status_code == 422


def test_run_returns_baseline_vs_scenario(api):
    sid = api.post("/api/v1/simulasi/scenarios", json=OVERRUN).json()["scenario_id"]
    body = api.post(f"/api/v1/simulasi/scenarios/{sid}/run").json()
    project = body["projects"][0]
    assert (project["baseline_finish"], project["scenario_finish"]) == ("2026-11-04", "2026-11-06")
    assert project["shift_days"] == 2
    assert body["tasks"][0]["change"] == "shifted"
    week = body["resource_load"][0]["scenario"][0]
    assert week == {"week_start": "2026-11-02", "capacity": 5.0, "used": 5.0}


def test_baseline_endpoint_lists_form_options(api):
    body = api.get("/api/v1/simulasi/baseline").json()
    assert body["data_source"] == "test"
    assert body["tasks"][0]["assignee_ids"] == ["R1"]
    assert {r["id"] for r in body["roles"]} == {"DEV", "QA"}
