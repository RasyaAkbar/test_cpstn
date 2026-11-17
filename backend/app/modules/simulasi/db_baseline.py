"""Membangun Snapshot baseline dari tabel dataset di database (langkah 1 desain IV.2.3).

PEMILIK: Orang 2 — Simulasi.

Dataset (puti_datasets.xlsx, dimuat oleh app/modules/data/importer.py) mencatat kondisi
proyek sampai tanggal observasi terakhir (`as_of`). Simulasi dimulai pada hari kerja
berikutnya dan hanya menjadwalkan pekerjaan yang masih terbuka.

Data PuTI tidak punya time tracking, sehingga beberapa nilai harus diturunkan. Aturannya
ada di bagian "Asumsi penyiapan data" dan diringkas di Snapshot.notes agar terlihat di
layar. Semua asumsi perlu dikonfirmasi ke PuTI saat validasi (III.3.3).
"""

import math
import statistics
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.data import models as db
from app.modules.simulasi.domain import (
    WORK_WEIGHTS,
    Assignment,
    Availability,
    Block,
    ComplexityLevel,
    Dependency,
    Holiday,
    Project,
    Resource,
    Role,
    Snapshot,
    Task,
    TaskRecord,
)

# ─── Asumsi penyiapan data ──────────────────────────────────────────────────────

# Porsi estimated_days yang masih tersisa per status task (progres tidak tercatat).
REMAINING_SHARE = {
    "not_started": 1.0,
    "on_hold": 1.0,
    "in_progress": 0.5,  # titik tengah: sudah mulai, progres tidak diketahui
    "blocked": 0.5,
    "in_qa": 0.2,  # tinggal verifikasi QA dan perbaikan kecil
}
DAILY_CAPACITY = 1.0  # hari-orang per hari kerja sebelum dipotong porsi BAU
MAX_BAU_SHARE = 0.8  # batas aman agar setiap anggota tetap punya kapasitas proyek
DEFAULT_BLOCK_DAYS = 5  # dipakai jika change_events tidak punya blocker dengan extension_days
SKIPPED_PROJECT_STATUSES = ("released",)  # sudah launch; tidak ada keputusan yang tersisa
SKIPPED_TASK_STATUSES = ("dropped",)


# ─── Membaca tabel ──────────────────────────────────────────────────────────────


@dataclass
class DatasetRows:
    roles: list[db.Role]
    complexity_levels: list[db.ComplexityLevel]
    projects: list[db.Project]
    resources: list[db.Resource]
    tasks: list[db.Task]
    task_dependencies: list[db.TaskDependency]
    assignments: list[db.Assignment]
    workload_items: list[db.WorkloadItem]
    availability: list[db.Availability]
    change_events: list[db.ChangeEvent]
    holidays: list[db.Holiday]


def latest_import(session: Session) -> db.DatasetImport | None:
    return session.scalars(
        select(db.DatasetImport).order_by(db.DatasetImport.import_id.desc()).limit(1)
    ).first()


def read_rows(session: Session) -> DatasetRows:
    def rows(model, order):
        return list(session.scalars(select(model).order_by(order)))

    return DatasetRows(
        roles=rows(db.Role, db.Role.role_id),
        complexity_levels=rows(db.ComplexityLevel, db.ComplexityLevel.complexity_id),
        projects=rows(db.Project, db.Project.project_id),
        resources=rows(db.Resource, db.Resource.resource_id),
        tasks=rows(db.Task, db.Task.task_id),
        task_dependencies=rows(db.TaskDependency, db.TaskDependency.dependency_id),
        assignments=rows(db.Assignment, db.Assignment.assignment_id),
        workload_items=rows(db.WorkloadItem, db.WorkloadItem.item_id),
        availability=rows(db.Availability, db.Availability.availability_id),
        change_events=rows(db.ChangeEvent, db.ChangeEvent.event_id),
        holidays=rows(db.Holiday, db.Holiday.holiday_date),
    )


def build_snapshot(session: Session) -> Snapshot | None:
    """Snapshot dari import terakhir; None jika dataset belum pernah diimpor."""
    record = latest_import(session)
    if record is None:
        return None
    return snapshot_from_rows(read_rows(session), record.data_source)


# ─── Kalender ───────────────────────────────────────────────────────────────────


def _is_working(value: date, holidays: set[date]) -> bool:
    return value.weekday() < 5 and value not in holidays


def _working_days(first: date, last: date, holidays: set[date]) -> int:
    """Jumlah hari kerja di [first, last] (inklusif)."""
    return sum(
        1
        for offset in range((last - first).days + 1)
        if _is_working(first + timedelta(days=offset), holidays)
    )


def _next_working_day(value: date, holidays: set[date]) -> date:
    value += timedelta(days=1)
    while not _is_working(value, holidays):
        value += timedelta(days=1)
    return value


def observed_until(rows: DatasetRows) -> date:
    """Tanggal kejadian terakhir yang tercatat (bukan rencana) di dataset."""
    observed = [
        *(d for t in rows.tasks for d in (t.actual_start, t.actual_finish)),
        *(d for a in rows.assignments for d in (a.assigned_date, a.released_date)),
        *(
            d
            for w in rows.workload_items
            for d in (w.received_date, w.started_date, w.resolved_date)
        ),
        *(e.event_date for e in rows.change_events),
    ]
    observed = [d for d in observed if d is not None]
    if observed:
        return max(observed)
    # Belum ada kejadian sama sekali: simulasikan dari awal proyek paling awal.
    return min(p.start_date for p in rows.projects) - timedelta(days=1)


# ─── Penurunan nilai dari data ──────────────────────────────────────────────────


def bau_shares(rows: DatasetRows, as_of: date, holidays: set[date]) -> dict[str, float]:
    """Porsi hari tiap anggota yang rutin habis untuk tiket dan operasional.

    Setiap item workload_items yang terbuka membebani pemiliknya sebesar
    bobot item / capacity_reference role per hari kerja (definisi RLI, FR-04.3).
    Porsi BAU = total beban itu dibagi hari kerja pengamatan anggota. Item yang belum
    resolved dihitung terbuka sampai as_of.
    """
    if not rows.workload_items:
        return {}
    capacity = {r.role_id: r.capacity_reference for r in rows.roles}
    role_of = {r.resource_id: r.primary_role_id for r in rows.resources}
    window_start = min(w.received_date for w in rows.workload_items)
    load: dict[str, float] = defaultdict(float)
    for w in rows.workload_items:
        opened = w.started_date or w.received_date
        closed = min(w.resolved_date or as_of, as_of)
        days = max(1, _working_days(opened, closed, holidays))
        load[w.resource_id] += days * WORK_WEIGHTS[w.item_type] / capacity[role_of[w.resource_id]]

    shares = {}
    for r in rows.resources:
        observed = _working_days(max(window_start, r.join_date), as_of, holidays)
        if observed > 0 and load.get(r.resource_id):
            shares[r.resource_id] = round(min(MAX_BAU_SHARE, load[r.resource_id] / observed), 3)
    return shares


def blocker_days(rows: DatasetRows) -> int:
    """Lama task `blocked` tertahan: rata-rata extension_days event blocker (dibulatkan ke atas)."""
    extensions = [
        e.extension_days
        for e in rows.change_events
        if e.event_type == "blocker" and e.extension_days > 0
    ]
    return math.ceil(statistics.mean(extensions)) if extensions else DEFAULT_BLOCK_DAYS


def _can_work(resource: db.Resource, role_id: str) -> bool:
    return resource.primary_role_id == role_id or (
        resource.cross_role_capable and role_id in resource.secondary_role_ids
    )


# ─── Snapshot ───────────────────────────────────────────────────────────────────


def snapshot_from_rows(rows: DatasetRows, data_source: str) -> Snapshot:
    holidays = {h.holiday_date for h in rows.holidays}
    as_of = observed_until(rows)
    start = _next_working_day(as_of, holidays)
    notes = [
        f"Kondisi data per {as_of.isoformat()} (kejadian terakhir yang tercatat); "
        f"simulasi mulai {start.isoformat()}."
    ]

    # Proyek: yang sudah rilis tidak disimulasikan.
    project_names = {p.project_id: p.project_name for p in rows.projects}
    active = [p for p in rows.projects if p.status not in SKIPPED_PROJECT_STATUSES]
    active_ids = {p.project_id for p in active}
    skipped_projects = [p.project_id for p in rows.projects if p.project_id not in active_ids]

    # Task: semua task proyek aktif kecuali yang di-drop.
    block_days = blocker_days(rows)
    tasks, blocks = [], []
    leftovers = dropped = 0
    for t in rows.tasks:
        if t.status in SKIPPED_TASK_STATUSES:
            dropped += 1
            continue
        if t.project_id not in active_ids:
            leftovers += t.status != "done"
            continue
        tasks.append(
            Task(
                task_id=t.task_id,
                project_id=t.project_id,
                task_name=t.task_name,
                required_role_id=t.required_role_id,
                complexity_id=t.complexity_id,
                priority_rank=t.priority_rank,
                estimated_days=t.estimated_days,
                phase=t.phase,
                status=t.status,
                remaining_share=REMAINING_SHARE.get(t.status, 1.0),
                planned_finish=t.planned_finish,
            )
        )
        if t.status == "blocked":
            blocks.append(Block(t.task_id, start, block_days))
    task_ids = {t.task_id for t in tasks}
    open_ids = {t.task_id for t in tasks if t.status != "done"}
    task_role = {t.task_id: t.required_role_id for t in tasks}

    if skipped_projects:
        notes.append(
            f"Proyek yang sudah rilis tidak disimulasikan ({', '.join(skipped_projects)}); "
            f"{leftovers} task terbuka di proyek tersebut diabaikan."
        )
    if dropped:
        notes.append(f"{dropped} task berstatus dropped tidak dijadwalkan.")
    notes.append(
        "Sisa effort (tanpa time tracking): not_started/on_hold 100%, in_progress/blocked 50%, "
        "in_qa 20% dari estimated_days."
    )
    if blocks:
        notes.append(
            f"{len(blocks)} task blocked dianggap tertahan {block_days} hari kerja sejak awal "
            "simulasi (rata-rata extension_days event blocker)."
        )

    # Assignment: hanya yang masih memegang task terbuka saat as_of. Data assignment
    # dianggap benar; role yang tidak tercatat di master anggota menjadi role sekunder.
    resource_rows = {r.resource_id: r for r in rows.resources}
    extra_roles: dict[str, set[str]] = defaultdict(set)
    assignments = []
    for a in rows.assignments:
        if a.task_id not in open_ids or (a.released_date and a.released_date <= as_of):
            continue
        role = task_role[a.task_id]
        if not _can_work(resource_rows[a.resource_id], role):
            extra_roles[a.resource_id].add(role)
        assignments.append(
            Assignment(
                task_id=a.task_id,
                resource_id=a.resource_id,
                assigned_date=a.assigned_date if a.assigned_date > as_of else None,
                released_date=a.released_date,
            )
        )
    if extra_roles:
        count = sum(len(roles) for roles in extra_roles.values())
        notes.append(
            f"{count} pasangan anggota–role hanya muncul di assignments; role itu dianggap "
            "role sekunder anggota (efisiensi lintas role)."
        )

    shares = bau_shares(rows, as_of, holidays)
    if shares:
        notes.append(
            "Kapasitas proyek harian = 1 hari-orang dikurangi porsi tiket/operasional historis "
            f"tiap anggota (median {statistics.median(shares.values()):.0%})."
        )
    resources = tuple(
        Resource(
            resource_id=r.resource_id,
            resource_name=r.resource_name,
            primary_role_id=r.primary_role_id,
            secondary_role_ids=tuple(
                r.secondary_role_ids
                + sorted(extra_roles[r.resource_id] - set(r.secondary_role_ids))
            ),
            cross_role_capable=r.cross_role_capable or bool(extra_roles[r.resource_id]),
            join_date=r.join_date,
            seniority=r.seniority,
            bau_share=shares.get(r.resource_id, 0.0),
        )
        for r in rows.resources
    )
    if holidays:
        notes.append(f"Hari libur di dataset tercatat sampai {max(holidays).isoformat()}.")

    return Snapshot(
        start_date=start,
        data_source=data_source,
        projects=tuple(
            Project(
                p.project_id, p.project_name, p.priority_rank, p.start_date, p.target_launch_date
            )
            for p in active
        ),
        roles=tuple(
            Role(r.role_id, r.role_name, DAILY_CAPACITY, r.capacity_reference) for r in rows.roles
        ),
        resources=resources,
        complexity_levels=tuple(
            ComplexityLevel(
                c.complexity_id, c.complexity_name, c.min_days, c.max_days, c.load_weight
            )
            for c in rows.complexity_levels
        ),
        tasks=tuple(tasks),
        dependencies=tuple(
            Dependency(d.task_id, d.depends_on_task_id, d.dependency_type, d.propagation_factor)
            for d in rows.task_dependencies
            if d.task_id in task_ids and d.depends_on_task_id in task_ids
        ),
        assignments=tuple(assignments),
        availability=tuple(
            Availability(a.resource_id, a.date_start, a.date_end, a.absence_type)
            for a in rows.availability
            if a.date_end >= start
        ),
        holidays=tuple(Holiday(h.holiday_date, h.holiday_name) for h in rows.holidays),
        blocks=tuple(blocks),
        as_of=as_of,
        notes=tuple(notes),
        history=tuple(
            TaskRecord(
                task_id=t.task_id,
                project_id=t.project_id,
                project_name=project_names[t.project_id],
                required_role_id=t.required_role_id,
                complexity_id=t.complexity_id,
                estimated_days=t.estimated_days,
                status=t.status,
                actual_start=t.actual_start,
                actual_finish=t.actual_finish,
                qa_reject_count=t.qa_reject_count,
            )
            for t in rows.tasks
        ),
    )
