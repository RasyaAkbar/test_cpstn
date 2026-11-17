"""KPI historis dari data aktual dataset (bukan hasil simulasi).

PEMILIK: Orang 3 — KPI.

  FR-04.8 Estimate Accuracy Ratio (EAR) = durasi aktual / durasi estimasi, per level
          kompleksitas dan per role. Durasi aktual = hari kerja actual_start s.d.
          actual_finish (inklusif) pada task berstatus done. Agregasi = Σ aktual / Σ estimasi,
          sehingga task besar berbobot sesuai ukurannya. 1.0 = estimasi tepat.
  FR-04.9 Rework Rate = task dengan qa_reject_count > 0 / task yang masuk fase QA
          (status in_qa atau done, atau pernah ditolak QA). Loop QA → developer menjadi
          proksi rework karena PuTI tidak punya time tracking.

Nilai ini tidak berubah antar skenario, jadi dihitung sekali per baseline. Sumbernya
Snapshot.history: semua task dataset, termasuk proyek yang sudah rilis.
"""

from collections import defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import timedelta

from app.modules.simulasi.domain import Snapshot, TaskRecord
from app.modules.simulasi.engine import WorkCalendar

QA_STATUSES = ("in_qa", "done")


@dataclass
class GroupRatio:
    key: str
    label: str
    value: float | None
    tasks: int


@dataclass
class HistoricalKpis:
    ear: float | None
    ear_by_complexity: list[GroupRatio]
    ear_by_role: list[GroupRatio]
    rework_rate: float | None  # %
    rework_by_role: list[GroupRatio]
    rework_by_project: list[GroupRatio]


def _grouped(
    records: Iterable[TaskRecord],
    key: Callable[[TaskRecord], str],
    labels: dict[str, str],
    numerator: Callable[[TaskRecord], float],
    denominator: Callable[[TaskRecord], float],
    scale: float,
) -> tuple[float | None, list[GroupRatio]]:
    sums: dict[str, list[float]] = defaultdict(lambda: [0.0, 0.0, 0])
    for r in records:
        group = sums[key(r)]
        group[0] += numerator(r)
        group[1] += denominator(r)
        group[2] += 1
    rows = [
        GroupRatio(
            key=k,
            label=labels.get(k, k),
            value=round(num / den * scale, 3) if den else None,
            tasks=int(n),
        )
        for k, (num, den, n) in sorted(sums.items())
    ]
    total_num = sum(v[0] for v in sums.values())
    total_den = sum(v[1] for v in sums.values())
    return (round(total_num / total_den * scale, 3) if total_den else None), rows


def historical_kpis(snapshot: Snapshot) -> HistoricalKpis:
    calendar = WorkCalendar(snapshot.start_date, {h.holiday_date for h in snapshot.holidays})
    roles = {r.role_id: r.role_name for r in snapshot.roles}
    levels = {c.complexity_id: c.complexity_name for c in snapshot.complexity_levels}

    finished = [
        r
        for r in snapshot.history
        if r.status == "done" and r.actual_start and r.actual_finish and r.estimated_days > 0
    ]
    # Hari kerja di [actual_start, actual_finish]; minimal 1 hari.
    actual = {
        r.task_id: max(
            1, calendar.working_days_between(r.actual_start - timedelta(days=1), r.actual_finish)
        )
        for r in finished
    }

    def ear(key, labels):
        return _grouped(
            finished, key, labels, lambda r: actual[r.task_id], lambda r: r.estimated_days, 1
        )

    ear_total, by_complexity = ear(lambda r: r.complexity_id, levels)
    _, by_role = ear(lambda r: r.required_role_id, roles)

    entered_qa = [r for r in snapshot.history if r.status in QA_STATUSES or r.qa_reject_count > 0]
    projects = {r.project_id: r.project_name for r in snapshot.history}

    def rework(key, labels):
        return _grouped(entered_qa, key, labels, lambda r: r.qa_reject_count > 0, lambda r: 1, 100)

    rework_total, rework_role = rework(lambda r: r.required_role_id, roles)
    _, rework_project = rework(lambda r: r.project_id, projects)

    return HistoricalKpis(
        ear=ear_total,
        ear_by_complexity=by_complexity,
        ear_by_role=by_role,
        rework_rate=rework_total,
        rework_by_role=rework_role,
        rework_by_project=rework_project,
    )
