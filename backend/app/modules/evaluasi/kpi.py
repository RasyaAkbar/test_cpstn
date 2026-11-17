"""Definisi dan perhitungan KPI satu hasil simulasi (KPI Calculator, Tabel 4.5).

PEMILIK: Orang 3 — KPI (Iterasi 2, FR-05). Rumus mengikuti "FR Dashboard Digital Twin -
Formula KPI" (FR-04.1 s.d. FR-04.10).

Masukan: SimulationResult dari app/modules/simulasi/engine.py (kontrak Orang 2).
Keluaran: KpiRun = nilai KPI + rincian per proyek, per anggota, dan per task.

KPI per run simulasi (dibandingkan antar skenario):
  FR-04.1  Schedule Variance (SV)              → projects_late, sv_total_days, sv_max_days
  FR-04.2  On-Time Launch Probability          → on_time_probability (dihitung comparison.py
                                                  dari replikasi; None di sini)
  FR-04.3  Resource Load Index (RLI)           → rli_peak, RLI mingguan per anggota
  FR-04.4  Overload Flag                       → overload_resource_weeks
  FR-04.5  Workload Balance Index (WBI)        → wbi
  FR-04.6  Sustained Overload Indicator (SOI)  → soi_max, sustained_overload_resources
  FR-04.7  Cascade Delay Impact (CDI)          → cdi_max, daftar task CDI terbesar
  FR-04.10 Blocked & Reallocated Time Ratio    → blocked_ratio, reallocated_ratio
FR-04.8 (EAR) dan FR-04.9 (Rework Rate) memakai data aktual, bukan hasil simulasi:
lihat historical.py.

Periode KPI mingguan = minggu ke-0 (awal snapshot) sampai minggu task terakhir selesai.
"""

import math
import statistics
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from typing import Literal

from app.modules.simulasi.domain import STARTED_STATUSES, WORK_WEIGHTS
from app.modules.simulasi.engine import SimulationResult

OVERLOAD_THRESHOLD = 1.0  # FR-04.4; bisa diubah per perbandingan (FR-04.11)
SOI_MIN_WEEKS = 2  # FR-04.6: overload dihitung berkelanjutan mulai 2 minggu berturut-turut
CASCADE_TOP = 10  # jumlah task CDI terbesar yang dikirim ke dashboard
DAYS_PER_WEEK = 7


# ─── Definisi KPI (satu sumber kebenaran; juga dikirim ke frontend) ─────────────


@dataclass(frozen=True)
class KpiDefinition:
    key: str
    fr: str  # nomor kebutuhan di FR Dashboard
    label: str
    unit: str
    better: Literal["lower", "higher"]  # arah nilai yang lebih baik
    description: str


KPI_DEFINITIONS: tuple[KpiDefinition, ...] = (
    KpiDefinition(
        "projects_late",
        "FR-04.1",
        "Proyek terlambat",
        "proyek",
        "lower",
        "Jumlah proyek dengan Schedule Variance > 0: launch hasil simulasi melewati target.",
    ),
    KpiDefinition(
        "sv_total_days",
        "FR-04.1",
        "Total Schedule Variance",
        "hari kerja",
        "lower",
        "SV = tanggal launch hasil simulasi − target launch (hari kerja). Jumlah SV positif "
        "seluruh proyek; proyek yang lebih cepat dari target dihitung 0.",
    ),
    KpiDefinition(
        "sv_max_days",
        "FR-04.1",
        "Schedule Variance terburuk",
        "hari kerja",
        "lower",
        "SV proyek yang paling terlambat. Negatif berarti semua proyek mendahului target.",
    ),
    KpiDefinition(
        "on_time_probability",
        "FR-04.2",
        "Peluang launch tepat waktu",
        "%",
        "higher",
        "Rata-rata seluruh proyek dari proporsi replikasi dengan SV ≤ 0. "
        "Hanya tersedia jika replikasi > 0.",
    ),
    KpiDefinition(
        "rli_peak",
        "FR-04.3",
        "Resource Load Index tertinggi",
        "indeks",
        "lower",
        "RLI(r,w) = (1.0 × task proyek aktif + 0.5 × item operasional + 0.3 × tiket terbuka) "
        "/ kapasitas referensi role. Nilai tertinggi dari semua anggota dan minggu.",
    ),
    KpiDefinition(
        "overload_resource_weeks",
        "FR-04.4",
        "Minggu-anggota overload",
        "minggu-orang",
        "lower",
        "Jumlah pasangan (anggota, minggu) dengan RLI di atas threshold overload.",
    ),
    KpiDefinition(
        "wbi",
        "FR-04.5",
        "Workload Balance Index",
        "indeks",
        "higher",
        "1 − koefisien variasi RLI antar anggota, dihitung per minggu lalu dirata-rata. "
        "1 berarti beban merata sempurna.",
    ),
    KpiDefinition(
        "soi_max",
        "FR-04.6",
        "Sustained Overload Indicator tertinggi",
        "indeks",
        "lower",
        "SOI(r) = jumlah minggu berturut-turut RLI di atas threshold (minimal 2) × rata-rata "
        "kelebihan RLI pada periode itu. Nilai anggota yang paling berat.",
    ),
    KpiDefinition(
        "sustained_overload_resources",
        "FR-04.6",
        "Anggota overload berkelanjutan",
        "orang",
        "lower",
        "Jumlah anggota dengan SOI > 0 (overload minimal 2 minggu berturut-turut).",
    ),
    KpiDefinition(
        "cdi_max",
        "FR-04.7",
        "Cascade Delay Impact tertinggi",
        "hari kerja",
        "lower",
        "CDI(t) = jumlah keterlambatan yang diteruskan task t ke seluruh task hilir (hard "
        "meneruskan penuh, soft sebesar faktor propagasi). Nilai task paling berdampak.",
    ),
    KpiDefinition(
        "blocked_ratio",
        "FR-04.10",
        "Blocked Time Ratio",
        "%",
        "lower",
        "Kapasitas yang menganggur karena task tertahan dependency/blocker dan tidak ada "
        "pekerjaan pengganti, dibagi total kapasitas kerja.",
    ),
    KpiDefinition(
        "reallocated_ratio",
        "FR-04.10",
        "Reallocated Time Ratio",
        "%",
        "higher",
        "Bagian waktu tunggu yang terisi task independen, dibagi total waktu tunggu "
        "(praktik pengalihan ke task independen di PuTI).",
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
    sv_days: int  # hari kerja; positif = terlambat, negatif = lebih cepat
    on_target: bool  # SV ≤ 0


@dataclass
class ResourceKpi:
    resource_id: str
    resource_name: str
    role_id: str
    weekly_rli: list[float | None]  # None = anggota tidak punya kapasitas minggu itu
    rli_peak: float
    rli_mean: float
    overload_weeks: int
    soi: float
    blocked_ratio: float | None  # %
    reallocated_ratio: float | None  # %


@dataclass
class TaskCascade:
    task_id: str
    task_name: str
    project_id: str
    delay_days: int  # keterlambatan task terhadap planned_finish (hari kerja)
    downstream_tasks: int
    cdi: float


@dataclass
class KpiRun:
    values: dict[str, float | None]
    projects: list[ProjectKpi]
    members: list[ResourceKpi]
    cascade: list[TaskCascade]
    week_starts: list[date]


# ─── FR-04.1 Schedule Variance ──────────────────────────────────────────────────


def project_kpis(result: SimulationResult) -> list[ProjectKpi]:
    rows = []
    for p in result.snapshot.projects:
        finish_day = result.project_finish_day(p.project_id)
        # Proyek belum selesai: SV dihitung sampai akhir horizon (batas bawah).
        finish = result.date_of(result.days_simulated if finish_day is None else finish_day)
        sv = result.calendar.working_days_between(p.target_launch_date, finish)
        rows.append(
            ProjectKpi(
                project_id=p.project_id,
                project_name=p.project_name,
                target_launch_date=p.target_launch_date,
                projected_finish=None if finish_day is None else finish,
                sv_days=sv,
                on_target=finish_day is not None and sv <= 0,
            )
        )
    return rows


# ─── FR-04.3 s.d. FR-04.6: beban mingguan per anggota ───────────────────────────


def period_days(result: SimulationResult) -> int:
    """Jumlah hari dari awal simulasi sampai task terakhir selesai (minimal 1)."""
    finishes = [o.finish_day for o in result.tasks.values()]
    if any(d is None for d in finishes):
        return max(1, result.days_simulated)
    return max(finishes, default=0) + 1


def _weeks_of(first: int, last: int) -> range:
    return range(first // DAYS_PER_WEEK, last // DAYS_PER_WEEK + 1)


def weekly_rli(result: SimulationResult, days: int) -> dict[str, list[float | None]]:
    """RLI(r,w) untuk setiap anggota dan minggu dalam periode KPI.

    - Task proyek aktif: task yang ditugaskan ke anggota, sejak mulai dikerjakan (atau sejak
      hari ke-0 jika sudah berjalan di baseline) sampai selesai.
    - Item operasional/tiket: porsi BAU historis anggota (Resource.bau_share, sudah dalam
      satuan RLI) ditambah item workload di snapshot (mis. hotfix skenario) selama terbuka.
    """
    s, cal = result.snapshot, result.calendar
    n_weeks = math.ceil(days / DAYS_PER_WEEK)
    last_day = days - 1
    started = {t.task_id for t in s.tasks if t.status in STARTED_STATUSES}

    # Minggu aktif per (anggota, task). Satu task bisa punya beberapa assignment ke anggota
    # yang sama (mis. pengganti cuti), jadi rentangnya digabung sebelum dihitung.
    spans: dict[tuple[str, str], list[range]] = defaultdict(list)
    for a in s.assignments:
        outcome = result.tasks.get(a.task_id)
        if outcome is None:
            continue  # task sudah selesai di baseline
        first = 0 if a.task_id in started else outcome.start_day
        if first is None:
            continue
        last = outcome.finish_day if outcome.finish_day is not None else last_day
        if a.assigned_date:
            first = max(first, cal.day_of(a.assigned_date))
        if a.released_date:
            last = min(last, cal.day_of(a.released_date) - 1)  # released_date eksklusif
        first, last = max(first, 0), min(last, last_day)
        if first <= last:
            spans[a.resource_id, a.task_id].append(_weeks_of(first, last))

    active: dict[str, list[int]] = defaultdict(lambda: [0] * (n_weeks + 1))
    for (rid, _), ranges in spans.items():
        diff = active[rid]  # array selisih: +1 di minggu awal, −1 setelah minggu akhir
        if len(ranges) == 1:
            diff[ranges[0].start] += 1
            diff[ranges[0].stop] -= 1
            continue
        for w in set().union(*ranges):
            diff[w] += 1
            diff[w + 1] -= 1
    for rid, diff in active.items():
        for w in range(1, n_weeks):
            diff[w] += diff[w - 1]

    extra: dict[str, list[float]] = defaultdict(lambda: [0.0] * n_weeks)
    for item in s.workload_items:
        first = max(0, cal.day_of(item.received_date))
        last = min(result.workload_done_day.get(item.item_id, last_day), last_day)
        for w in _weeks_of(first, last) if first <= last else ():
            extra[item.resource_id][w] += WORK_WEIGHTS.get(item.item_type, WORK_WEIGHTS["ticket"])

    rli: dict[str, list[float | None]] = {}
    for r in s.resources:
        capacity_ref = s.role_by_id[r.primary_role_id].capacity_reference
        daily = result.resources[r.resource_id].capacity
        series: list[float | None] = []
        for w in range(n_weeks):
            if sum(daily[w * DAYS_PER_WEEK : min((w + 1) * DAYS_PER_WEEK, days)]) <= 0:
                series.append(None)  # cuti/belum bergabung/keluar sepanjang minggu
                continue
            planned = WORK_WEIGHTS["project"] * active[r.resource_id][w]
            value = (planned + extra[r.resource_id][w]) / capacity_ref + r.bau_share
            series.append(round(value, 3))
        rli[r.resource_id] = series
    return rli


def sustained_overload(series: list[float | None], threshold: float) -> float:
    """SOI = panjang episode overload × rata-rata kelebihan; episode terberat (FR-04.6)."""
    best, run = 0.0, []
    for value in [*series, None]:  # None di akhir menutup episode terakhir
        if value is not None and value > threshold:
            run.append(value - threshold)
            continue
        if len(run) >= SOI_MIN_WEEKS:
            best = max(best, len(run) * statistics.fmean(run))
        run = []
    return round(best, 3)


def workload_balance(rli: dict[str, list[float | None]]) -> float | None:
    """WBI = rata-rata mingguan dari 1 − CV(RLI antar anggota yang tersedia) (FR-04.5)."""
    weekly = []
    for week in zip(*rli.values(), strict=True):
        values = [v for v in week if v is not None]
        if len(values) >= 2 and statistics.fmean(values) > 0:
            weekly.append(1 - statistics.pstdev(values) / statistics.fmean(values))
    return round(statistics.fmean(weekly), 3) if weekly else None


# ─── FR-04.7 Cascade Delay Impact ───────────────────────────────────────────────


def cascade_delay(result: SimulationResult) -> list[TaskCascade]:
    """CDI(t) = keterlambatan t × Σ faktor propagasi ke setiap task hilir yang terbuka.

    Faktor jalur = hasil kali propagation_factor di sepanjang jalur (hard 1.0, soft 0.3);
    jika ada beberapa jalur ke task yang sama, dipakai jalur terkuat. Keterlambatan task
    = hari kerja dari planned_finish ke tanggal selesai hasil simulasi (task tanpa
    planned_finish, mis. task CR baru, tidak punya keterlambatan).
    """
    s, cal = result.snapshot, result.calendar
    succ: dict[str, list[tuple[str, float]]] = defaultdict(list)
    for d in s.dependencies:
        if d.task_id in result.tasks and d.depends_on_task_id in result.tasks:
            succ[d.depends_on_task_id].append((d.task_id, d.propagation_factor))

    rows = []
    for tid, outcome in result.tasks.items():
        task = s.task_by_id[tid]
        if task.planned_finish is None or tid not in succ:
            continue
        finish = result.date_of(
            result.days_simulated if outcome.finish_day is None else outcome.finish_day
        )
        delay = max(0, cal.working_days_between(task.planned_finish, finish))
        if delay == 0:
            continue
        # Faktor terkuat ke setiap task hilir. Faktor ≤ 1, jadi relaksasi berulang berhenti.
        strength: dict[str, float] = {}
        stack = [(tid, 1.0)]
        while stack:
            node, factor = stack.pop()
            for child, f in succ.get(node, ()):
                value = factor * f
                if value > strength.get(child, 0.0) + 1e-12:
                    strength[child] = value
                    stack.append((child, value))
        rows.append(
            TaskCascade(
                task_id=tid,
                task_name=task.task_name,
                project_id=task.project_id,
                delay_days=delay,
                downstream_tasks=len(strength),
                cdi=round(delay * sum(strength.values()), 2),
            )
        )
    rows.sort(key=lambda r: (-r.cdi, r.task_id))
    return rows


# ─── FR-04.10 Blocked dan Reallocated Time Ratio ────────────────────────────────


def _ratio(part: float, whole: float) -> float | None:
    return round(part / whole * 100, 2) if whole > 1e-9 else None


def waiting_totals(result: SimulationResult, rid: str, days: int) -> tuple[float, float, float]:
    """(kapasitas, kapasitas menganggur saat menunggu, kapasitas saat bertemu task tertahan)."""
    out = result.resources[rid]
    return sum(out.capacity[:days]), sum(out.idle_waiting[:days]), sum(out.wait_capacity[:days])


# ─── Semua KPI satu run ─────────────────────────────────────────────────────────


def compute_kpis(
    result: SimulationResult, threshold: float = OVERLOAD_THRESHOLD, detail: bool = True
) -> KpiRun:
    """Hitung KPI satu run. detail=False melewati CDI (hanya dibutuhkan run deterministik,
    agar replikasi Monte Carlo tetap cepat)."""
    s = result.snapshot
    projects = project_kpis(result)
    days = period_days(result)
    rli = weekly_rli(result, days)

    members, totals = [], [0.0, 0.0, 0.0]
    for r in s.resources:
        series = rli[r.resource_id]
        present = [v for v in series if v is not None]
        capacity, idle, wait = waiting_totals(result, r.resource_id, days)
        totals = [totals[0] + capacity, totals[1] + idle, totals[2] + wait]
        members.append(
            ResourceKpi(
                resource_id=r.resource_id,
                resource_name=r.resource_name,
                role_id=r.primary_role_id,
                weekly_rli=series,
                rli_peak=max(present, default=0.0),
                rli_mean=round(statistics.fmean(present), 3) if present else 0.0,
                overload_weeks=sum(1 for v in present if v > threshold),
                soi=sustained_overload(series, threshold),
                blocked_ratio=_ratio(idle, capacity),
                reallocated_ratio=_ratio(wait - idle, wait),
            )
        )

    cascade = cascade_delay(result) if detail else []
    sv = [p.sv_days for p in projects]
    values: dict[str, float | None] = {
        "projects_late": sum(1 for v in sv if v > 0),
        "sv_total_days": sum(max(0, v) for v in sv),
        "sv_max_days": max(sv, default=0),
        "on_time_probability": None,  # diisi comparison.py dari replikasi
        "rli_peak": max((m.rli_peak for m in members), default=0.0),
        "overload_resource_weeks": sum(m.overload_weeks for m in members),
        "wbi": workload_balance(rli),
        "soi_max": max((m.soi for m in members), default=0.0),
        "sustained_overload_resources": sum(1 for m in members if m.soi > 0),
        "cdi_max": max((c.cdi for c in cascade), default=0.0) if detail else None,
        "blocked_ratio": _ratio(totals[1], totals[0]),
        "reallocated_ratio": _ratio(totals[2] - totals[1], totals[2]),
    }
    n_weeks = math.ceil(days / DAYS_PER_WEEK)
    return KpiRun(
        values={k: None if v is None else float(v) for k, v in values.items()},
        projects=projects,
        members=members,
        cascade=cascade[:CASCADE_TOP],
        week_starts=[result.date_of(w * DAYS_PER_WEEK) for w in range(n_weeks)],
    )
