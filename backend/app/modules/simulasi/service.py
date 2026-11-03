"""Orkestrasi simulasi dan penyusunan respons API (UC-03 jalankan, UC-04 lihat hasil).

PEMILIK: Orang 2 — Simulasi (Iterasi 1, FR-03/FR-04).

simulate_pair() juga dipakai modul evaluasi (Orang 3), jadi tanda tangannya adalah kontrak.
"""

from datetime import date

from app.modules.simulasi.domain import Snapshot
from app.modules.simulasi.engine import SimulationResult, run_simulation
from app.modules.simulasi.rules import apply_scenario
from app.modules.simulasi.schemas import (
    BaselineProject,
    BaselineResource,
    BaselineResponse,
    BaselineTask,
    Option,
    ProjectOutcome,
    ResourceLoad,
    Scenario,
    SimulationRunResponse,
    TaskChange,
    WeeklyLoad,
)


def simulate_pair(
    baseline: Snapshot, scenario: Scenario
) -> tuple[SimulationResult, SimulationResult]:
    """Jalankan baseline dan skenario secara deterministik. Raise ScenarioError jika invalid."""
    scenario_snapshot = apply_scenario(baseline, scenario.parameters)
    return run_simulation(baseline), run_simulation(scenario_snapshot)


# ─── GET /simulasi/baseline: daftar pilihan untuk form skenario ─────────────────


def baseline_response(s: Snapshot) -> BaselineResponse:
    assignees: dict[str, list[str]] = {}
    for a in s.assignments:
        assignees.setdefault(a.task_id, []).append(a.resource_id)
    return BaselineResponse(
        data_source=s.data_source,
        start_date=s.start_date,
        projects=[BaselineProject(**vars(p)) for p in s.projects],
        resources=[
            BaselineResource(
                resource_id=r.resource_id,
                resource_name=r.resource_name,
                primary_role_id=r.primary_role_id,
                secondary_role_ids=list(r.secondary_role_ids),
            )
            for r in s.resources
        ],
        tasks=[
            BaselineTask(
                task_id=t.task_id,
                project_id=t.project_id,
                task_name=t.task_name,
                required_role_id=t.required_role_id,
                complexity_id=t.complexity_id,
                estimated_days=t.estimated_days,
                status=t.status,
                assignee_ids=assignees.get(t.task_id, []),
            )
            for t in s.tasks
        ],
        roles=[Option(id=r.role_id, name=r.role_name) for r in s.roles],
        complexity_levels=[
            Option(
                id=c.complexity_id, name=f"{c.complexity_name} ({c.min_days:g}–{c.max_days:g} hari)"
            )
            for c in s.complexity_levels
        ],
    )


# ─── POST /simulasi/scenarios/{id}/run: hasil simulasi untuk layar Simulation result ─


def _date(result: SimulationResult, day: int | None) -> date | None:
    return None if day is None else result.date_of(day)


def _shift(before: date | None, after: date | None) -> int | None:
    return None if before is None or after is None else (after - before).days


def _project_outcomes(base: SimulationResult, scen: SimulationResult) -> list[ProjectOutcome]:
    rows = []
    for project in scen.snapshot.projects:
        b = _date(base, base.project_finish_day(project.project_id))
        s = _date(scen, scen.project_finish_day(project.project_id))
        rows.append(
            ProjectOutcome(
                project_id=project.project_id,
                project_name=project.project_name,
                target_launch_date=project.target_launch_date,
                baseline_finish=b,
                scenario_finish=s,
                shift_days=_shift(b, s),
            )
        )
    return rows


def _task_changes(base: SimulationResult, scen: SimulationResult) -> list[TaskChange]:
    names = {t.task_id: t for t in (*base.snapshot.tasks, *scen.snapshot.tasks)}
    removed = set(scen.snapshot.removed_task_ids)
    rows = []
    for tid in sorted(set(base.tasks) | set(scen.tasks), key=lambda t: (names[t].project_id, t)):
        b, s = base.tasks.get(tid), scen.tasks.get(tid)
        b_start, b_finish = (
            (_date(base, b.start_day), _date(base, b.finish_day)) if b else (None, None)
        )
        s_start, s_finish = (
            (_date(scen, s.start_day), _date(scen, s.finish_day)) if s else (None, None)
        )
        if tid in removed:
            change = "removed"
        elif b is None:
            change = "added"
        elif (b_start, b_finish) != (s_start, s_finish):
            change = "shifted"
        else:
            change = "unchanged"
        rows.append(
            TaskChange(
                task_id=tid,
                project_id=names[tid].project_id,
                task_name=names[tid].task_name,
                change=change,
                baseline_start=b_start,
                baseline_finish=b_finish,
                scenario_start=s_start,
                scenario_finish=s_finish,
                shift_days=_shift(b_finish, s_finish),
            )
        )
    return rows


def _weekly(result: SimulationResult, resource_id: str, weeks: int) -> list[WeeklyLoad]:
    out = result.resources.get(resource_id)
    rows = []
    for w in range(weeks):
        days = range(w * 7, min((w + 1) * 7, result.days_simulated))
        cap = sum(out.capacity[d] for d in days) if out else 0.0
        used = sum(out.used_project[d] + out.used_workload[d] for d in days) if out else 0.0
        rows.append(
            WeeklyLoad(
                week_start=result.date_of(w * 7), capacity=round(cap, 2), used=round(used, 2)
            )
        )
    return rows


def _resource_load(base: SimulationResult, scen: SimulationResult) -> list[ResourceLoad]:
    weeks = (max(base.days_simulated, scen.days_simulated) + 6) // 7
    return [
        ResourceLoad(
            resource_id=r.resource_id,
            resource_name=r.resource_name,
            baseline=_weekly(base, r.resource_id, weeks),
            scenario=_weekly(scen, r.resource_id, weeks),
        )
        for r in scen.snapshot.resources  # termasuk anggota baru dari skenario
    ]


def run_response(
    scenario: Scenario, base: SimulationResult, scen: SimulationResult
) -> SimulationRunResponse:
    return SimulationRunResponse(
        scenario=scenario,
        data_source=scen.snapshot.data_source,
        projects=_project_outcomes(base, scen),
        tasks=_task_changes(base, scen),
        resource_load=_resource_load(base, scen),
        warnings=scen.warnings,
    )
