"""Perbandingan KPI baseline vs skenario dan pemilihan skenario terbaik (KPI Comparator).

PEMILIK: Orang 3 — KPI (Iterasi 2, FR-06, UC-05/UC-06).

Alur compare():
  1. Jalankan baseline dan setiap skenario (deterministik + replikasi Monte Carlo).
  2. Hitung KPI tiap run dengan kpi.compute_kpis().
  3. Ringkas replikasi menjadi median, P10, P90 (agar hasil tidak tampak lebih presisi
     daripada sebenarnya, Law 2015), dan hitung On-Time Launch Probability (FR-04.2).
  4. Hitung delta skenario − baseline dan tandai lebih baik/lebih buruk.
  5. Urutkan skenario dengan RANKING_ORDER, lalu pilih skenario terbaik.
"""

import math

from app.modules.evaluasi.kpi import (
    KPI_BY_KEY,
    KPI_DEFINITIONS,
    OVERLOAD_THRESHOLD,
    KpiRun,
    compute_kpis,
)
from app.modules.evaluasi.schemas import (
    CompareResponse,
    Distribution,
    Evaluation,
    KpiValue,
    ProjectKpiOut,
    ResourceKpiOut,
    TaskCascadeOut,
)
from app.modules.simulasi.domain import Snapshot
from app.modules.simulasi.engine import SimulationResult, run_replications, run_simulation
from app.modules.simulasi.rules import apply_scenario
from app.modules.simulasi.schemas import Scenario

# Urutan kriteria skenario terbaik (leksikografis): launch tepat waktu dulu, lalu besar
# keterlambatan, lalu kesehatan beban tim. Dipilih karena mudah dijelaskan ke stakeholder.
RANKING_ORDER = (
    "projects_late",
    "sv_total_days",
    "sustained_overload_resources",
    "overload_resource_weeks",
    "wbi",
)
TOLERANCE = 1e-6


# ─── Langkah 3: ringkasan replikasi ─────────────────────────────────────────────


def percentile(values: list[float], q: float) -> float:
    """Persentil dengan interpolasi linear (q dalam 0..1)."""
    ordered = sorted(values)
    pos = (len(ordered) - 1) * q
    low = int(pos)
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (pos - low)


def _distribution(runs: list[KpiRun], key: str) -> Distribution | None:
    values = [r.values[key] for r in runs if r.values[key] is not None]
    if not values:
        return None
    return Distribution(
        median=round(percentile(values, 0.5), 2),
        p10=round(percentile(values, 0.1), 2),
        p90=round(percentile(values, 0.9), 2),
    )


def on_time_probabilities(runs: list[KpiRun]) -> dict[str, float]:
    """FR-04.2: porsi replikasi dengan SV ≤ 0, per proyek."""
    hits: dict[str, int] = {}
    for run in runs:
        for p in run.projects:
            hits[p.project_id] = hits.get(p.project_id, 0) + p.on_target
    return {pid: round(n / len(runs), 3) for pid, n in hits.items()}


# ─── Langkah 4: delta dan status terhadap baseline ──────────────────────────────


def kpi_status(key: str, delta: float) -> str:
    if abs(delta) <= TOLERANCE:
        return "same"
    lower_better = KPI_BY_KEY[key].better == "lower"
    return "better" if (delta < 0) == lower_better else "worse"


def _evaluation(
    scenario_id: str | None,
    name: str,
    det: SimulationResult,
    det_kpi: KpiRun,
    rep_kpis: list[KpiRun],
    baseline: Evaluation | None,
) -> Evaluation:
    probability = on_time_probabilities(rep_kpis) if rep_kpis else {}
    values = dict(det_kpi.values)
    if probability:
        values["on_time_probability"] = round(sum(probability.values()) / len(probability) * 100, 1)

    base_values = {k.key: k.value for k in baseline.kpis} if baseline else {}
    kpis = []
    for definition in KPI_DEFINITIONS:
        key = definition.key
        value, base = values[key], base_values.get(key)
        delta = None if value is None or base is None else round(value - base, 2)
        kpis.append(
            KpiValue(
                key=key,
                value=value,
                distribution=_distribution(rep_kpis, key) if rep_kpis else None,
                delta=delta,
                status=None if delta is None else kpi_status(key, delta),
            )
        )
    return Evaluation(
        scenario_id=scenario_id,
        name=name,
        kpis=kpis,
        projects=[
            ProjectKpiOut(**vars(p), on_target_probability=probability.get(p.project_id))
            for p in det_kpi.projects
        ],
        members=[ResourceKpiOut(**vars(m)) for m in det_kpi.members],
        cascade=[TaskCascadeOut(**vars(c)) for c in det_kpi.cascade],
        week_starts=det_kpi.week_starts,
        warnings=det.warnings,
    )


# ─── Langkah 5: peringkat skenario ──────────────────────────────────────────────


def _rank_value(key: str, value: float | None) -> float:
    """Nilai untuk diurutkan naik: KPI "higher" dibalik, nilai kosong paling akhir."""
    if value is None:
        return math.inf
    return value if KPI_BY_KEY[key].better == "lower" else -value


def rank_scenarios(evaluations: list[Evaluation]) -> list[str]:
    def key(e: Evaluation) -> tuple:
        values = {k.key: k.value for k in e.kpis}
        return (*(_rank_value(k, values.get(k)) for k in RANKING_ORDER), e.scenario_id)

    return [e.scenario_id for e in sorted(evaluations, key=key)]


# ─── Langkah 1–5 ────────────────────────────────────────────────────────────────


def compare(
    baseline: Snapshot,
    scenarios: list[Scenario],
    replications: int,
    seed: int,
    threshold: float = OVERLOAD_THRESHOLD,
) -> CompareResponse:
    """Raise ScenarioError (dari simulasi.rules) jika parameter skenario tidak valid."""

    def kpis_of(result: SimulationResult, detail: bool = True) -> KpiRun:
        return compute_kpis(result, threshold, detail)

    def replicated(snapshot: Snapshot) -> list[KpiRun]:
        # Replikasi ke-i skenario memakai angka acak per task yang sama dengan replikasi
        # ke-i baseline (common random numbers, lihat engine.run_replications).
        return [kpis_of(r, detail=False) for r in run_replications(snapshot, replications, seed)]

    base_det = run_simulation(baseline)
    baseline_eval = _evaluation(
        None, "Baseline", base_det, kpis_of(base_det), replicated(baseline), None
    )

    evaluations = []
    for scenario in scenarios:
        snap = apply_scenario(baseline, scenario.parameters)
        det = run_simulation(snap)
        evaluations.append(
            _evaluation(
                scenario.scenario_id,
                scenario.name,
                det,
                kpis_of(det),
                replicated(snap),
                baseline_eval,
            )
        )

    ranking = rank_scenarios(evaluations)
    return CompareResponse(
        data_source=baseline.data_source,
        replications=replications,
        overload_threshold=threshold,
        baseline=baseline_eval,
        scenarios=evaluations,
        best_scenario_id=ranking[0] if ranking else None,
        ranking=ranking,
        ranking_basis=[KPI_BY_KEY[k].label for k in RANKING_ORDER],
    )
