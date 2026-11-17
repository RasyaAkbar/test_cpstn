"""Mesin simulasi what-if (Simulation Engine, Tabel 4.5).

PEMILIK: Orang 2 — Simulasi (Iterasi 1, FR-03).

Mengikuti lima langkah desain IV.2.3:
  1. Muat snapshot baseline                    → parameter `snapshot` (dari baseline.py)
  2. Terapkan perubahan skenario                → rules.apply_scenario() SEBELUM modul ini
  3. Hitung kapasitas harian tiap anggota       → WorkCalendar + _capacity_profile()
  4. Jadwalkan task hari demi hari              → _schedule()
  5. Catat start/finish task dan beban anggota  → SimulationResult (dibaca modul evaluasi/KPI)

Ketidakpastian effort: run_replications() mengulang simulasi dengan effort tiap task
diambil dari distribusi segitiga antara min_days dan max_days level kompleksitasnya.
Modul ini TIDAK menghitung KPI; KPI dihitung Orang 3 di app/modules/evaluasi/kpi.py.
"""

import random
from dataclasses import dataclass, field
from datetime import date, timedelta

from app.modules.simulasi.domain import Resource, Snapshot, Task

EPS = 1e-9
HORIZON_DAYS = 730  # batas aman: berhenti setelah 2 tahun kalender
CROSS_ROLE_EFFICIENCY = 0.75  # asumsi: kerja di role sekunder 75% seefektif role utama


# ─── Hasil simulasi (kontrak untuk Orang 3 / KPI) ───────────────────────────────


@dataclass
class TaskOutcome:
    task_id: str
    project_id: str
    effort_days: float  # effort yang dipakai di run ini (estimasi atau sampel)
    start_day: int | None = None  # indeks hari (0 = snapshot.start_date)
    finish_day: int | None = None  # None = belum selesai sampai horizon
    dependency_ready_day: int | None = None  # hari pertama semua predecessor terpenuhi
    # Kapasitas (hari-orang) yang dihabiskan tiap anggota pada task ini
    spent_by_resource: dict[str, float] = field(default_factory=dict)


@dataclass
class ResourceOutcome:
    resource_id: str
    capacity: list[float]  # kapasitas proyek per hari (setelah cuti, BAU, onboarding, mentor)
    used_project: list[float] = field(default_factory=list)  # dipakai task proyek
    used_workload: list[float] = field(default_factory=list)  # dipakai tiket/hotfix
    idle_waiting: list[float] = field(default_factory=list)  # hilang karena dependency/blocker
    # Kapasitas yang tersisa saat anggota bertemu task prioritasnya yang tertahan. Bagian
    # yang tidak menjadi idle_waiting dialihkan ke task independen (FR-04.10).
    wait_capacity: list[float] = field(default_factory=list)


@dataclass
class SimulationResult:
    snapshot: Snapshot
    calendar: "WorkCalendar"
    tasks: dict[str, TaskOutcome]
    resources: dict[str, ResourceOutcome]
    days_simulated: int  # panjang semua list harian di ResourceOutcome
    warnings: list[str]
    workload_done_day: dict[str, int] = field(default_factory=dict)  # item_id → hari selesai

    def date_of(self, day: int) -> date:
        return self.calendar.date_of(day)

    def project_finish_day(self, project_id: str) -> int | None:
        """Hari task terakhir proyek selesai; None jika ada task yang belum selesai.

        Proyek tanpa task terbuka dianggap siap launch di hari ke-0.
        """
        days = [o.finish_day for o in self.tasks.values() if o.project_id == project_id]
        if not days:
            return 0
        return None if any(d is None for d in days) else max(days)


# ─── Langkah 3: kalender kerja dan kapasitas harian ─────────────────────────────


class WorkCalendar:
    """Hari kerja = Senin–Jumat dan bukan hari libur (holidays.csv)."""

    def __init__(self, start: date, holidays: set[date]):
        self.start = start
        self.holidays = frozenset(holidays)
        self._working = [
            self.is_working_date(start + timedelta(days=d)) for d in range(HORIZON_DAYS)
        ]

    def date_of(self, day: int) -> date:
        return self.start + timedelta(days=day)

    def day_of(self, value: date) -> int:
        return (value - self.start).days

    def is_working(self, day: int) -> bool:
        return 0 <= day < HORIZON_DAYS and self._working[day]

    def is_working_date(self, value: date) -> bool:
        return value.weekday() < 5 and value not in self.holidays

    def working_days_between(self, first: date, second: date) -> int:
        """Hari kerja di (first, second]; negatif jika second sebelum first.

        Dipakai untuk Schedule Variance (FR-04.1): launch Jumat dengan target Kamis = +1.
        """
        if second == first:
            return 0
        low, high = sorted((first, second))
        count = sum(
            1 for d in range(1, (high - low).days + 1) if self.is_working_date(low + timedelta(d))
        )
        return count if second > first else -count


def _onboarding_factor(resource: Resource, worked_days: int) -> float:
    """Ramp-up linear dari initial_capacity ke 1.0 selama onboarding_days hari kerja."""
    if resource.onboarding_days <= 0 or worked_days >= resource.onboarding_days:
        return 1.0
    step = (1.0 - resource.initial_capacity) / resource.onboarding_days
    return resource.initial_capacity + step * worked_days


def _capacity_profile(snapshot: Snapshot, calendar: WorkCalendar) -> dict[str, list[float]]:
    """Kapasitas proyek harian tiap anggota untuk seluruh horizon.

    Tidak bergantung pada effort task, jadi cukup dihitung sekali per snapshot dan dipakai
    ulang oleh semua replikasi. Urutan potongan: hari kerja → cuti → join/keluar →
    porsi BAU (tiket/operasional rutin) → ramp-up onboarding → overhead mentor.
    """
    absent: dict[str, set[int]] = {}
    for a in snapshot.availability:
        first, last = calendar.day_of(a.date_start), calendar.day_of(a.date_end)
        absent.setdefault(a.resource_id, set()).update(range(first, last + 1))

    profile: dict[str, list[float]] = {}
    onboarding_until: dict[str, int] = {}  # hari terakhir onboarding tiap anggota baru
    for r in snapshot.resources:
        base = snapshot.role_by_id[r.primary_role_id].daily_capacity * (1 - r.bau_share)
        join = calendar.day_of(r.join_date) if r.join_date else -1
        leave = calendar.day_of(r.leave_date) if r.leave_date else HORIZON_DAYS
        days_out = absent.get(r.resource_id, set())
        worked, caps = 0, []
        for day in range(HORIZON_DAYS):
            if not calendar.is_working(day) or day in days_out or day < join or day >= leave:
                caps.append(0.0)
                continue
            caps.append(base * _onboarding_factor(r, worked))
            worked += 1
            if r.onboarding_days and worked == r.onboarding_days:
                onboarding_until[r.resource_id] = day
        profile[r.resource_id] = caps

    # Mentor kehilangan `overhead` hari-orang pada hari mentee bekerja selama onboarding.
    for m in snapshot.mentorships:
        mentor, mentee = profile[m.mentor_id], profile[m.mentee_id]
        last = onboarding_until.get(m.mentee_id, -1)
        for day in range(min(last + 1, HORIZON_DAYS)):
            if mentee[day] > 0:
                mentor[day] = max(0.0, mentor[day] - m.overhead)
    return profile


def _role_efficiency(resource: Resource, task: Task) -> float | None:
    """1.0 untuk role utama, CROSS_ROLE_EFFICIENCY untuk role sekunder, None jika tidak cocok."""
    if resource.primary_role_id == task.required_role_id:
        return 1.0
    if resource.cross_role_capable and task.required_role_id in resource.secondary_role_ids:
        return CROSS_ROLE_EFFICIENCY
    return None


# ─── Persiapan: semua yang tidak bergantung pada effort (dipakai ulang replikasi) ─


@dataclass
class _Prepared:
    calendar: WorkCalendar
    capacity: dict[str, list[float]]
    preds: dict[str, list[tuple[str, float]]]  # task → [(predecessor, propagation_factor)]
    blocked: dict[str, set[int]]  # task → hari kerja yang diblokir
    work_list: dict[
        str, list[tuple[Task, float, int, int]]
    ]  # anggota → (task, efisiensi, mulai, lepas)
    earliest: dict[str, int]  # task → hari paling awal boleh mulai
    workload: dict[str, list[tuple[int, float, str]]]  # anggota → (hari masuk, effort, id)
    last_target_day: int
    warnings: list[str]


def _prepare(snapshot: Snapshot) -> _Prepared:
    calendar = WorkCalendar(snapshot.start_date, {h.holiday_date for h in snapshot.holidays})
    open_tasks = snapshot.open_tasks()
    open_ids = {t.task_id for t in open_tasks}
    warnings: list[str] = []

    # Predecessor yang sudah "done" di baseline tidak menahan task.
    preds: dict[str, list[tuple[str, float]]] = {tid: [] for tid in open_ids}
    for dep in snapshot.dependencies:
        if dep.task_id in open_ids and dep.depends_on_task_id in open_ids:
            preds[dep.task_id].append((dep.depends_on_task_id, dep.propagation_factor))

    blocked: dict[str, set[int]] = {}
    for b in snapshot.blocks:
        day, left = calendar.day_of(b.date_start), b.working_days
        while left > 0 and day < HORIZON_DAYS:
            if calendar.is_working(day):
                blocked.setdefault(b.task_id, set()).add(day)
                left -= 1
            day += 1

    def priority(task: Task) -> tuple[int, int, str]:
        project = snapshot.project_by_id[task.project_id]
        return (project.priority_rank, task.priority_rank, task.task_id)

    work_list: dict[str, list[tuple[Task, float, int, int]]] = {
        r.resource_id: [] for r in snapshot.resources
    }
    staffed: set[str] = set()
    for a in snapshot.assignments:
        task = snapshot.task_by_id.get(a.task_id)
        resource = snapshot.resource_by_id.get(a.resource_id)
        if task is None or resource is None or task.task_id not in open_ids:
            continue
        eff = _role_efficiency(resource, task)
        if eff is None:
            warnings.append(
                f"{resource.resource_id} tidak punya role {task.required_role_id} untuk "
                f"{task.task_id}; assignment diabaikan"
            )
            continue
        start = calendar.day_of(a.assigned_date) if a.assigned_date else -HORIZON_DAYS
        end = calendar.day_of(a.released_date) if a.released_date else HORIZON_DAYS
        work_list[resource.resource_id].append((task, eff, start, end))
        staffed.add(task.task_id)
    for items in work_list.values():
        # Anggota lintas proyek mengerjakan prioritas tertinggi dulu (praktik PuTI, Tabel 1.1).
        items.sort(key=lambda item: priority(item[0]))
    warnings += [
        f"{tid} tidak punya anggota yang bisa mengerjakan" for tid in sorted(open_ids - staffed)
    ]

    earliest = {}
    for t in open_tasks:
        days = [calendar.day_of(snapshot.project_by_id[t.project_id].start_date)]
        if t.earliest_start:
            days.append(calendar.day_of(t.earliest_start))
        earliest[t.task_id] = max(days)

    workload: dict[str, list[tuple[int, float, str]]] = {}
    for w in sorted(
        snapshot.workload_items, key=lambda w: (not w.is_hotfix, w.received_date, w.item_id)
    ):
        workload.setdefault(w.resource_id, []).append(
            (calendar.day_of(w.received_date), w.effort_days, w.item_id)
        )

    return _Prepared(
        calendar=calendar,
        capacity=_capacity_profile(snapshot, calendar),
        preds=preds,
        blocked=blocked,
        work_list=work_list,
        earliest=earliest,
        workload=workload,
        last_target_day=max(calendar.day_of(p.target_launch_date) for p in snapshot.projects),
        warnings=warnings,
    )


# ─── Langkah 4 & 5: penjadwalan hari demi hari dan pencatatan hasil ─────────────


def _schedule(snapshot: Snapshot, prep: _Prepared, effort: dict[str, float]) -> SimulationResult:
    outcomes = {
        t.task_id: TaskOutcome(t.task_id, t.project_id, effort[t.task_id])
        for t in snapshot.open_tasks()
    }
    remaining = dict(effort)
    # Effort total (termasuk bagian yang sudah dikerjakan sebelum snapshot), agar
    # propagation_factor dibandingkan dengan progres task, bukan progres sisa effort.
    total = {
        t.task_id: effort[t.task_id] / t.remaining_share if t.remaining_share > EPS else 0.0
        for t in snapshot.open_tasks()
    }
    wl_left = {rid: [list(item) for item in items] for rid, items in prep.workload.items()}
    wl_done: dict[str, int] = {}
    resources_out = {rid: ResourceOutcome(rid, prep.capacity[rid]) for rid in prep.capacity}
    unfinished = set(outcomes)
    # Progres hanya bertambah, jadi task yang predecessor-nya sudah terpenuhi tetap
    # terpenuhi: cukup periksa task yang belum terpenuhi.
    deps_pending = set(outcomes)
    deps_met: set[str] = set()
    # Daftar kerja per anggota; task selesai dibuang dari daftar pemiliknya keesokan hari.
    work_list = {rid: list(items) for rid, items in prep.work_list.items()}
    owners: dict[str, set[str]] = {}
    for rid, items in work_list.items():
        for item in items:
            owners.setdefault(item[0].task_id, set()).add(rid)
    stale: set[str] = set()

    day = 0
    while day < HORIZON_DAYS:
        wl_open = any(item[1] > EPS for items in wl_left.values() for item in items)
        if not unfinished and not wl_open and day > prep.last_target_day:
            break
        if not prep.calendar.is_working(day):
            # Akhir pekan/libur: semua kapasitas 0, tidak ada progres yang bisa berubah.
            for out in resources_out.values():
                for series in (out.used_workload, out.used_project, out.idle_waiting):
                    series.append(0.0)
                out.wait_capacity.append(0.0)
            day += 1
            continue
        for rid in stale:
            work_list[rid] = [item for item in work_list[rid] if item[0].task_id in unfinished]
        stale.clear()

        # Kesiapan dievaluasi di awal hari agar urutan anggota tidak memengaruhi hasil.
        # Task siap jika setiap predecessor sudah selesai minimal sebesar propagation_factor.
        for tid in [t for t in deps_pending if day >= prep.earliest[t]]:
            if all(
                total[p] <= EPS or 1 - remaining[p] / total[p] >= f - EPS
                for p, f in prep.preds[tid]
            ):
                deps_pending.discard(tid)
                deps_met.add(tid)
                outcomes[tid].dependency_ready_day = day
        ready = {tid for tid in deps_met if day not in prep.blocked.get(tid, ())}

        for rid, out in resources_out.items():
            cap = out.capacity[day]
            if cap <= EPS:  # cuti/belum bergabung: tidak ada yang bisa dikerjakan
                for series in (out.used_workload, out.used_project, out.idle_waiting):
                    series.append(0.0)
                out.wait_capacity.append(0.0)
                continue

            # Tiket/hotfix mendahului fitur (praktik PuTI: "hotfix goes first").
            used_wl = 0.0
            for item in wl_left.get(rid, ()):
                if cap <= EPS:
                    break
                if item[0] <= day and item[1] > EPS:
                    spent = min(cap, item[1])
                    item[1] -= spent
                    cap -= spent
                    used_wl += spent
                    if item[1] <= EPS:
                        wl_done[item[2]] = day
            out.used_workload.append(used_wl)

            used_prj = 0.0
            # Kapasitas saat anggota pertama kali bertemu task prioritasnya yang tertahan
            # dependency/blocker; None = tidak ada task tertahan yang menahan kapasitas.
            wait_cap: float | None = None
            for task, eff, a_start, a_end in work_list[rid]:
                tid = task.task_id
                if tid not in unfinished or not (a_start <= day < a_end):
                    continue
                if tid not in ready:
                    if wait_cap is None and cap > EPS and day >= prep.earliest[tid]:
                        wait_cap = cap
                    continue
                if cap <= EPS:
                    continue
                work = min(cap * eff, remaining[tid])
                remaining[tid] -= work
                cap -= work / eff
                used_prj += work / eff
                spent = outcomes[tid].spent_by_resource
                spent[rid] = spent.get(rid, 0.0) + work / eff
                if outcomes[tid].start_day is None:
                    outcomes[tid].start_day = day
                if remaining[tid] <= EPS:
                    outcomes[tid].finish_day = day
                    unfinished.discard(tid)
                    deps_met.discard(tid)
                    stale |= owners[tid]
            out.used_project.append(used_prj)
            # Kapasitas tersisa padahal ada task milik anggota yang tertahan = hilang karena
            # menunggu (Blocked Ratio). Kapasitas yang tetap terpakai setelah bertemu task
            # tertahan = dialihkan ke task independen (Reallocated Ratio, FR-04.10).
            waiting = wait_cap is not None
            out.idle_waiting.append(cap if waiting and cap > EPS else 0.0)
            out.wait_capacity.append(wait_cap if waiting else 0.0)
        day += 1

    for out in resources_out.values():
        out.capacity = out.capacity[:day]  # samakan panjang dengan list harian lain
    warnings = list(prep.warnings)
    if unfinished:
        warnings.append(f"{len(unfinished)} task belum selesai sampai batas horizon simulasi")
    return SimulationResult(
        snapshot, prep.calendar, outcomes, resources_out, day, warnings, wl_done
    )


def run_simulation(snapshot: Snapshot) -> SimulationResult:
    """Satu run deterministik dengan effort = sisa estimasi (nilai utama yang ditampilkan)."""
    effort = {t.task_id: t.remaining_days for t in snapshot.open_tasks()}
    return _schedule(snapshot, _prepare(snapshot), effort)


# ─── Ketidakpastian effort: replikasi Monte Carlo (desain IV.2.3 paragraf akhir) ─


def sample_effort(snapshot: Snapshot, task: Task, rng: random.Random) -> float:
    """Distribusi segitiga [min_days, max_days] dengan modus = estimated_days, lalu dikali
    porsi effort yang masih tersisa."""
    level = snapshot.complexity_by_id[task.complexity_id]
    low = min(level.min_days, task.estimated_days)
    high = max(level.max_days, task.estimated_days)
    if high - low < EPS:
        return task.remaining_days
    return rng.triangular(low, high, task.estimated_days) * task.remaining_share


def run_replications(snapshot: Snapshot, replications: int, seed: int) -> list[SimulationResult]:
    """Jalankan `replications` run dengan effort acak.

    Seed per (seed, replikasi, task_id): task yang sama mendapat angka acak yang sama di
    baseline dan skenario (common random numbers), sehingga selisih KPI mencerminkan
    skenario, bukan kebetulan sampel.
    """
    prep = _prepare(snapshot)
    results = []
    for rep in range(replications):
        effort = {
            t.task_id: sample_effort(snapshot, t, random.Random(f"{seed}:{rep}:{t.task_id}"))
            for t in snapshot.open_tasks()
        }
        results.append(_schedule(snapshot, prep, effort))
    return results
