"""Aturan skenario: menerapkan parameter skenario ke SALINAN baseline (langkah 2 IV.2.3).

PEMILIK: Orang 2 — Simulasi (Iterasi 1, FR-03).

Satu fungsi `_apply_<situasi>` per situasi keputusan di Tabel 4.2. Setiap fungsi hanya
mengubah data (task, assignment, cuti, kapasitas); penjadwalan tetap dilakukan engine.py.
Aturan berasal dari praktik PuTI di Tabel 1.1, misalnya cuti mendadak ditutup anggota
dengan role sama dan hotfix mendahului fitur.
"""

from dataclasses import replace
from datetime import date, timedelta

from app.modules.simulasi.domain import (
    Assignment,
    Availability,
    Block,
    Dependency,
    Mentorship,
    Resource,
    Snapshot,
    Task,
    WorkloadItem,
)
from app.modules.simulasi.schemas import (
    ChangeRequestParams,
    CriticalBugParams,
    MemberAbsenceParams,
    NewMemberParams,
    PriorityChangeParams,
    RotationParams,
    ScenarioParameters,
    TaskBlockerParams,
    TaskOverrunParams,
)


class ScenarioError(ValueError):
    """Parameter skenario merujuk data yang tidak ada atau tidak bisa diterapkan."""


# ─── Validasi referensi dan pemilihan pengganti ─────────────────────────────────


def _project(s: Snapshot, project_id: str):
    if project_id not in s.project_by_id:
        raise ScenarioError(f"Proyek {project_id} tidak ada di baseline")
    return s.project_by_id[project_id]


def _resource(s: Snapshot, resource_id: str) -> Resource:
    if resource_id not in s.resource_by_id:
        raise ScenarioError(f"Anggota {resource_id} tidak ada di baseline")
    return s.resource_by_id[resource_id]


def _open_task(s: Snapshot, task_id: str) -> Task:
    task = s.task_by_id.get(task_id)
    if task is None:
        raise ScenarioError(f"Task {task_id} tidak ada di baseline")
    if task.status == "done":
        raise ScenarioError(f"Task {task_id} sudah selesai di baseline")
    return task


def _check_date(s: Snapshot, value: date, label: str) -> None:
    if value < s.start_date:
        raise ScenarioError(f"{label} ({value}) sebelum awal baseline ({s.start_date})")


def _assigned_effort(s: Snapshot, resource_id: str) -> float:
    open_ids = {t.task_id for t in s.open_tasks()}
    return sum(
        s.task_by_id[a.task_id].estimated_days
        for a in s.assignments
        if a.resource_id == resource_id and a.task_id in open_ids and a.released_date is None
    )


def pick_cover(s: Snapshot, role_id: str, exclude: set[str]) -> Resource:
    """Anggota role utama sama dengan beban tugas terkecil; jika tidak ada, anggota
    cross-role yang punya role itu sebagai role sekunder."""
    primary = [r for r in s.resources if r.primary_role_id == role_id]
    secondary = [r for r in s.resources if r.cross_role_capable and role_id in r.secondary_role_ids]
    for group in (primary, secondary):
        candidates = [r for r in group if r.resource_id not in exclude and r.leave_date is None]
        if candidates:
            return min(
                candidates, key=lambda r: (_assigned_effort(s, r.resource_id), r.resource_id)
            )
    raise ScenarioError(f"Tidak ada anggota lain dengan role {role_id}")


# ─── Satu fungsi per situasi (Tabel 4.2) ────────────────────────────────────────


def _apply_change_request(s: Snapshot, p: ChangeRequestParams) -> Snapshot:
    _project(s, p.project_id)
    _check_date(s, p.request_date, "Tanggal CR")
    for tid in p.remove_task_ids:
        if _open_task(s, tid).project_id != p.project_id:
            raise ScenarioError(f"Task {tid} bukan bagian dari proyek {p.project_id}")
    removed = set(p.remove_task_ids)

    tasks = [t for t in s.tasks if t.task_id not in removed]
    deps = [
        d
        for d in s.dependencies
        if d.task_id not in removed and d.depends_on_task_id not in removed
    ]
    assignments = [a for a in s.assignments if a.task_id not in removed]
    working = replace(s, tasks=tuple(tasks), assignments=tuple(assignments))

    for i, new in enumerate(p.add_tasks, start=1):
        if new.required_role_id not in s.role_by_id:
            raise ScenarioError(f"Role {new.required_role_id} tidak ada")
        if new.complexity_id not in s.complexity_by_id:
            raise ScenarioError(f"Level kompleksitas {new.complexity_id} tidak ada")
        task_id = f"CR-{p.project_id.removeprefix('PRJ-')}{i:02d}"
        tasks.append(
            Task(
                task_id,
                p.project_id,
                new.task_name,
                new.required_role_id,
                new.complexity_id,
                new.priority_rank,
                new.estimated_days,
                "change_request",
                earliest_start=p.request_date,
            )
        )
        for pred in new.depends_on_task_ids:
            if pred not in s.task_by_id or pred in removed:
                raise ScenarioError(f"Predecessor {pred} tidak ada")
            deps.append(Dependency(task_id, pred))
        if new.assignee_id:
            assignee = _resource(s, new.assignee_id)
        else:
            assignee = pick_cover(working, new.required_role_id, set())
        assignments.append(Assignment(task_id, assignee.resource_id, p.request_date))

    return replace(
        s,
        tasks=tuple(tasks),
        dependencies=tuple(deps),
        assignments=tuple(assignments),
        removed_task_ids=s.removed_task_ids + tuple(sorted(removed)),
    )


def _apply_member_absence(s: Snapshot, p: MemberAbsenceParams) -> Snapshot:
    absent = _resource(s, p.resource_id)
    _check_date(s, p.date_start, "Awal absen")
    availability = s.availability + (
        Availability(p.resource_id, p.date_start, p.date_end, p.absence_type),
    )
    assignments = list(s.assignments)

    if p.cover_resource_id or p.auto_cover:
        # Pengganti ikut ditugaskan pada task anggota yang absen selama periode absen.
        # Setelah anggota kembali, task kembali dikerjakan pemilik awal.
        open_ids = {t.task_id for t in s.open_tasks()}
        exclude = {absent.resource_id}
        for a in s.assignments:
            if a.resource_id != absent.resource_id or a.task_id not in open_ids:
                continue
            role = s.task_by_id[a.task_id].required_role_id
            if p.cover_resource_id:
                cover = _resource(s, p.cover_resource_id)
            else:
                cover = pick_cover(s, role, exclude)
            assignments.append(
                Assignment(
                    a.task_id, cover.resource_id, p.date_start, p.date_end + timedelta(days=1)
                )
            )
    return replace(s, availability=availability, assignments=tuple(assignments))


def _apply_new_member(s: Snapshot, p: NewMemberParams) -> Snapshot:
    if p.role_id not in s.role_by_id:
        raise ScenarioError(f"Role {p.role_id} tidak ada")
    _check_date(s, p.join_date, "Tanggal bergabung")
    new_id = f"NEW-{len(s.resources) + 1:02d}"
    member = Resource(
        new_id,
        p.resource_name,
        p.role_id,
        seniority=p.seniority,
        join_date=p.join_date,
        onboarding_days=p.onboarding_days,
        initial_capacity=p.initial_capacity,
    )

    if p.assist_task_ids:
        targets = [_open_task(s, tid) for tid in p.assist_task_ids]
    elif p.project_id:
        _project(s, p.project_id)
        targets = [
            t
            for t in s.open_tasks()
            if t.project_id == p.project_id and t.required_role_id == p.role_id
        ]
    else:
        raise ScenarioError("Isi project_id atau assist_task_ids untuk anggota baru")
    if not targets:
        raise ScenarioError("Tidak ada task terbuka yang bisa dibantu anggota baru")

    # Anggota baru ditambahkan sebagai rekan kerja, pemilik lama tetap mengerjakan task.
    assignments = s.assignments + tuple(Assignment(t.task_id, new_id, p.join_date) for t in targets)
    mentorships = s.mentorships
    if p.mentor_resource_id:
        _resource(s, p.mentor_resource_id)
        mentorships += (Mentorship(p.mentor_resource_id, new_id, p.mentor_overhead),)
    return replace(
        s, resources=s.resources + (member,), assignments=assignments, mentorships=mentorships
    )


def _apply_rotation(s: Snapshot, p: RotationParams) -> Snapshot:
    moving = _resource(s, p.resource_id)
    _project(s, p.from_project_id)
    _check_date(s, p.transfer_date, "Tanggal rotasi")
    open_ids = {t.task_id for t in s.open_tasks()}
    assignments: list[Assignment] = []
    handed_over: list[Task] = []
    for a in s.assignments:
        task = s.task_by_id.get(a.task_id)
        leaving = (
            a.resource_id == moving.resource_id
            and task is not None
            and a.task_id in open_ids
            and (p.to_project_id is None or task.project_id == p.from_project_id)
        )
        if leaving:
            assignments.append(replace(a, released_date=p.transfer_date))
            handed_over.append(task)
        else:
            assignments.append(a)

    if p.replacement_resource_id or p.auto_replacement:
        for task in handed_over:
            if p.replacement_resource_id:
                repl = _resource(s, p.replacement_resource_id)
            else:
                repl = pick_cover(s, task.required_role_id, {moving.resource_id})
            assignments.append(Assignment(task.task_id, repl.resource_id, p.transfer_date))

    resources = s.resources
    if p.to_project_id:
        _project(s, p.to_project_id)
        already = {a.task_id for a in s.assignments if a.resource_id == moving.resource_id}
        for task in s.open_tasks():
            joins = task.project_id == p.to_project_id and task.task_id not in already
            if joins and task.required_role_id == moving.primary_role_id:
                assignments.append(Assignment(task.task_id, moving.resource_id, p.transfer_date))
    else:
        # Withdrawal: anggota keluar dari unit; kapasitasnya nol sejak tanggal transfer.
        resources = tuple(
            replace(r, leave_date=p.transfer_date) if r.resource_id == moving.resource_id else r
            for r in s.resources
        )
    return replace(s, resources=resources, assignments=tuple(assignments))


def _apply_task_overrun(s: Snapshot, p: TaskOverrunParams) -> Snapshot:
    _open_task(s, p.task_id)
    tasks = tuple(
        replace(t, estimated_days=p.revised_estimated_days) if t.task_id == p.task_id else t
        for t in s.tasks
    )
    return replace(s, tasks=tasks)


def _apply_task_blocker(s: Snapshot, p: TaskBlockerParams) -> Snapshot:
    _open_task(s, p.task_id)
    _check_date(s, p.block_start, "Awal blocker")
    return replace(s, blocks=s.blocks + (Block(p.task_id, p.block_start, p.block_days),))


def _apply_priority_change(s: Snapshot, p: PriorityChangeParams) -> Snapshot:
    _project(s, p.project_id)
    projects = tuple(
        replace(
            proj,
            priority_rank=p.new_priority_rank or proj.priority_rank,
            target_launch_date=p.new_target_launch_date or proj.target_launch_date,
        )
        if proj.project_id == p.project_id
        else proj
        for proj in s.projects
    )
    new_rank = {tp.task_id: tp.priority_rank for tp in p.task_priorities}
    for tid in new_rank:
        if _open_task(s, tid).project_id != p.project_id:
            raise ScenarioError(f"Task {tid} bukan bagian dari proyek {p.project_id}")
    tasks = tuple(
        replace(t, priority_rank=new_rank[t.task_id]) if t.task_id in new_rank else t
        for t in s.tasks
    )
    return replace(s, projects=projects, tasks=tasks)


def _apply_critical_bug(s: Snapshot, p: CriticalBugParams) -> Snapshot:
    _resource(s, p.resource_id)
    _check_date(s, p.report_date, "Tanggal laporan bug")
    if p.related_project_id:
        _project(s, p.related_project_id)
    item = WorkloadItem(
        f"BUG-{len(s.workload_items) + 1:02d}",
        p.resource_id,
        "hotfix",
        p.related_project_id,
        p.report_date,
        p.fix_days,
        p.severity,
        is_hotfix=True,
    )
    return replace(s, workload_items=s.workload_items + (item,))


_RULES = {
    "change_request": _apply_change_request,
    "member_absence": _apply_member_absence,
    "new_member": _apply_new_member,
    "rotation": _apply_rotation,
    "task_overrun": _apply_task_overrun,
    "task_blocker": _apply_task_blocker,
    "priority_change": _apply_priority_change,
    "critical_bug": _apply_critical_bug,
}


def apply_scenario(baseline: Snapshot, params: ScenarioParameters) -> Snapshot:
    """Kembalikan snapshot baru; `baseline` tidak pernah diubah."""
    return _RULES[params.situation](baseline, params)
