"""Definisi dan perhitungan KPI untuk satu hasil simulasi (KPI Calculator, Tabel 4.5).

PEMILIK: Orang 3 — KPI (Iterasi 2, FR-05).

Masukan: SimulationResult dari app/modules/simulasi/engine.py (kontrak Orang 2).
Keluaran: KpiRun = nilai KPI + rincian per proyek + beban per anggota.

KPI diturunkan dari "Candidate KPIs" di I.4.2 proposal:
  projected completion date & delay  → total_delay_days, max_delay_days, completion_span_days
  load per member against capacity   → overloaded_members, max_member_load_pct
  tasks delayed through dependencies → tasks_delayed_by_dependency
  launch target still holds          → projects_missing_target
  tasks dropped or deferred          → tasks_dropped_or_deferred
  (gap "capacity lost to dependencies", Tabel 1.1) → idle_capacity_days
Set KPI final masih perlu dikonfirmasi dengan PuTI; tambah/ubah KPI cukup di file ini.
"""

from dataclasses import dataclass
from datetime import date
from typing import Literal

from app.modules.simulasi.engine import SimulationResult

OVERLOAD_THRESHOLD_PCT = 100.0  # beban > 100% kapasitas = overload
LOAD_PCT_CAP = 999.0  # anggota tanpa kapasitas tetapi punya pekerjaan


# ─── Definisi KPI (satu sumber kebenaran; juga dikirim ke frontend) ─────────────


@dataclass(frozen=True)
class KpiDefinition:
    key: str
    label: str
    unit: str
    better: Literal["lower", "higher"]  # arah nilai yang lebih baik
    description: str


KPI_DEFINITIONS: tuple[KpiDefinition, ...] = (
    KpiDefinition(
        "projects_missing_target",
        "Proyek melewati target launch",
        "proyek",
        "lower",
        "Jumlah proyek yang selesai setelah target_launch_date atau belum selesai.",
    ),
    KpiDefinition(
        "total_delay_days",
        "Total keterlambatan",
        "hari",
        "lower",
        "Jumlah hari kalender keterlambatan semua proyek terhadap target launch. "
        "Proyek yang tepat waktu dihitung 0.",
    ),
    KpiDefinition(
        "max_delay_days",
        "Keterlambatan terbesar",
        "hari",
        "lower",
        "Keterlambatan proyek yang paling parah terhadap target launch-nya.",
    ),
    KpiDefinition(
        "completion_span_days",
        "Durasi sampai semua proyek selesai",
        "hari",
        "lower",
        "Hari kalender dari awal baseline sampai proyek terakhir selesai (projected completion).",
    ),
    KpiDefinition(
        "overloaded_members",
        "Anggota overload",
        "orang",
        "lower",
        "Anggota dengan beban kerja di atas 100% kapasitasnya sampai target proyek "
        "yang ia kerjakan.",
    ),
    KpiDefinition(
        "max_member_load_pct",
        "Beban anggota tertinggi",
        "%",
        "lower",
        "Beban kerja / kapasitas anggota yang paling tinggi.",
    ),
    KpiDefinition(
        "tasks_delayed_by_dependency",
        "Task tertunda karena dependency",
        "task",
        "lower",
        "Task yang predecessor-nya baru terpenuhi lebih lambat daripada di baseline.",
    ),
    KpiDefinition(
        "tasks_dropped_or_deferred",
        "Task di-drop atau lewat target",
        "task",
        "lower",
        "Task yang dihapus skenario ditambah task yang selesai setelah target launch proyeknya.",
    ),
    KpiDefinition(
        "idle_capacity_days",
        "Kapasitas hilang karena menunggu",
        "hari-orang",
        "lower",
        "Kapasitas anggota yang tidak terpakai karena task-nya tertahan dependency atau blocker.",
    ),
)
KPI_BY_KEY = {k.key: k for k in KPI_DEFINITIONS}


# ─── Rincian hasil perhitungan ──────────────────────────────────────────────────


@dataclass
class ProjectKpi:
    project_id: str
    project_name: str
    target_launch_date: date
    projected_finish: date | None  # None = belum selesai sampai horizon simulasi
    delay_days: int  # 0 jika tepat waktu
    on_target: bool


@dataclass
class MemberLoad:
    resource_id: str
    resource_name: str
    demand_days: float  # hari-orang pekerjaan yang ditanggung anggota
    capacity_days: float  # hari-orang tersedia sampai target proyek terakhirnya
    load_pct: float
    overloaded: bool


@dataclass
class KpiRun:
    values: dict[str, float]
    projects: list[ProjectKpi]
    members: list[MemberLoad]


# ─── Perhitungan per KPI ────────────────────────────────────────────────────────


def project_kpis(result: SimulationResult) -> list[ProjectKpi]:
    rows = []
    for p in result.snapshot.projects:
        finish_day = result.project_finish_day(p.project_id)
        # Proyek belum selesai: dihitung terlambat minimal sampai akhir horizon.
        effective = result.date_of(result.days_simulated if finish_day is None else finish_day)
        delay = max(0, (effective - p.target_launch_date).days)
        rows.append(
            ProjectKpi(
                project_id=p.project_id,
                project_name=p.project_name,
                target_launch_date=p.target_launch_date,
                projected_finish=None if finish_day is None else effective,
                delay_days=delay,
                on_target=finish_day is not None and delay == 0,
            )
        )
    return rows


def member_loads(result: SimulationResult) -> list[MemberLoad]:
    """Beban = pekerjaan yang ditanggung anggota / kapasitasnya sampai target proyeknya.

    Pekerjaan (demand) = kapasitas yang benar-benar dihabiskan di task proyek dan
    tiket/hotfix, ditambah sisa task yang belum selesai dibagi rata ke pemiliknya.
    Pekerjaan yang dikerjakan setelah target tetap dihitung, sehingga beban > 100%
    berarti anggota tidak bisa menyelesaikan bagiannya sebelum target launch.
    """
    s = result.snapshot
    target_day = {p.project_id: result.calendar.day_of(p.target_launch_date) for p in s.projects}
    last_target = max(target_day.values())
    demand: dict[str, float] = {r.resource_id: 0.0 for r in s.resources}
    deadline: dict[str, int] = {}

    for outcome in result.tasks.values():
        for rid, spent in outcome.spent_by_resource.items():
            demand[rid] += spent
            deadline[rid] = max(deadline.get(rid, -1), target_day[outcome.project_id])
        if outcome.finish_day is None:
            owners = [
                a.resource_id
                for a in s.assignments
                if a.task_id == outcome.task_id and a.released_date is None
            ]
            left = max(0.0, outcome.effort_days - sum(outcome.spent_by_resource.values()))
            for rid in owners:
                demand[rid] += left / len(owners)
                deadline[rid] = max(deadline.get(rid, -1), target_day[outcome.project_id])

    rows = []
    for r in s.resources:
        out = result.resources[r.resource_id]
        demand[r.resource_id] += sum(out.used_workload)
        until = deadline.get(r.resource_id, last_target)
        capacity = sum(out.capacity[: until + 1])
        need = demand[r.resource_id]
        if capacity > 0:
            load = min(LOAD_PCT_CAP, need / capacity * 100)
        else:
            load = LOAD_PCT_CAP if need > 0 else 0.0
        rows.append(
            MemberLoad(
                resource_id=r.resource_id,
                resource_name=r.resource_name,
                demand_days=round(need, 2),
                capacity_days=round(capacity, 2),
                load_pct=round(load, 1),
                overloaded=load > OVERLOAD_THRESHOLD_PCT,
            )
        )
    return rows


def tasks_delayed_by_dependency(result: SimulationResult, reference: SimulationResult) -> int:
    """Task yang dependency-nya terpenuhi lebih lambat dari di `reference` (baseline)."""
    count = 0
    for tid, outcome in result.tasks.items():
        ref = reference.tasks.get(tid)
        if ref is None or ref.dependency_ready_day is None:
            continue  # task baru dari CR tidak punya pembanding
        if (
            outcome.dependency_ready_day is None
            or outcome.dependency_ready_day > ref.dependency_ready_day
        ):
            count += 1
    return count


def tasks_dropped_or_deferred(result: SimulationResult) -> int:
    s = result.snapshot
    target = {p.project_id: p.target_launch_date for p in s.projects}
    deferred = sum(
        1
        for o in result.tasks.values()
        if o.finish_day is None or result.date_of(o.finish_day) > target[o.project_id]
    )
    return len(s.removed_task_ids) + deferred


def compute_kpis(result: SimulationResult, reference: SimulationResult) -> KpiRun:
    """Hitung semua KPI satu run. `reference` = run baseline yang sepadan (untuk baseline
    sendiri, isi dengan run yang sama sehingga KPI dependency bernilai 0)."""
    projects = project_kpis(result)
    members = member_loads(result)
    finish_days = [result.project_finish_day(p.project_id) for p in result.snapshot.projects]
    values = {
        "projects_missing_target": sum(1 for p in projects if not p.on_target),
        "total_delay_days": sum(p.delay_days for p in projects),
        "max_delay_days": max((p.delay_days for p in projects), default=0),
        "completion_span_days": max(result.days_simulated if d is None else d for d in finish_days),
        "overloaded_members": sum(1 for m in members if m.overloaded),
        "max_member_load_pct": max((m.load_pct for m in members), default=0.0),
        "tasks_delayed_by_dependency": tasks_delayed_by_dependency(result, reference),
        "tasks_dropped_or_deferred": tasks_dropped_or_deferred(result),
        "idle_capacity_days": round(
            sum(sum(out.idle_waiting) for out in result.resources.values()), 2
        ),
    }
    return KpiRun({k: float(v) for k, v in values.items()}, projects, members)
