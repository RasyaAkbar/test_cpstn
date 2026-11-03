"""Perbandingan KPI baseline vs skenario dan pemilihan skenario terbaik (KPI Comparator).

PEMILIK: Orang 3 — KPI (Iterasi 2, FR-06, UC-05/UC-06).

Alur compare():
  1. Jalankan baseline dan setiap skenario (deterministik + replikasi Monte Carlo).
  2. Hitung KPI tiap run dengan kpi.compute_kpis().
  3. Ringkas replikasi menjadi median, P10, P90 (agar hasil tidak tampak lebih presisi
     daripada sebenarnya, Law 2015).
  4. Hitung delta skenario − baseline dan tandai lebih baik/lebih buruk.
  5. Urutkan skenario dengan RANKING_ORDER, lalu pilih skenario terbaik.
"""

from app.modules.evaluasi.kpi import KPI_BY_KEY, KPI_DEFINITIONS, KpiRun, compute_kpis
from app.modules.evaluasi.schemas import (
    CompareResponse,
    Distribution,
    Evaluation,
    KpiValue,
    MemberLoadOut,
    ProjectKpiOut,
)
from app.modules.simulasi.domain import Snapshot
from app.modules.simulasi.engine import SimulationResult, run_replications, run_simulation
from app.modules.simulasi.rules import apply_scenario
from app.modules.simulasi.schemas import Scenario

# Urutan kriteria skenario terbaik (leksikografis): target launch dulu, lalu besar
# keterlambatan, lalu beban anggota. Dipilih karena mudah dijelaskan ke stakeholder.
RANKING_ORDER = (
    "projects_missing_target",
    "total_delay_days",
    "overloaded_members",
    "max_member_load_pct",
    "completion_span_days",
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


def _distribution(runs: list[KpiRun], key: str) -> Distribution:
    values = [r.values[key] for r in runs]
    return Distribution(
        median=round(percentile(values, 0.5), 2),
        p10=round(percentile(values, 0.1), 2),
        p90=round(percentile(values, 0.9), 2),
    )


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
    baseline_kpi: KpiRun | None,
) -> Evaluation:
    kpis = []
    for definition in KPI_DEFINITIONS:
        key = definition.key
        value = det_kpi.values[key]
        delta = None if baseline_kpi is None else round(value - baseline_kpi.values[key], 2)
        kpis.append(
            KpiValue(
                key=key,
                value=value,
                distribution=_distribution(rep_kpis, key) if rep_kpis else None,
                delta=delta,
                status=None if delta is None else kpi_status(key, delta),
            )
        )
    projects = []
    for p in det_kpi.projects:
        probability = None
        if rep_kpis:
            hits = sum(
                1
                for run in rep_kpis
                for rp in run.projects
                if rp.project_id == p.project_id and rp.on_target
            )
            probability = round(hits / len(rep_kpis), 3)
        projects.append(ProjectKpiOut(**vars(p), on_target_probability=probability))
    return Evaluation(
        scenario_id=scenario_id,
        name=name,
        kpis=kpis,
        projects=projects,
        members=[MemberLoadOut(**vars(m)) for m in det_kpi.members],
        warnings=det.warnings,
    )


# ─── Langkah 5: peringkat skenario ──────────────────────────────────────────────


def rank_scenarios(evaluations: list[Evaluation]) -> list[str]:
    def key(e: Evaluation) -> tuple:
        values = {k.key: k.value for k in e.kpis}
        return (*(values[k] for k in RANKING_ORDER), e.scenario_id)

    return [e.scenario_id for e in sorted(evaluations, key=key)]


# ─── Langkah 1–5 ────────────────────────────────────────────────────────────────


def compare(
    baseline: Snapshot, scenarios: list[Scenario], replications: int, seed: int
) -> CompareResponse:
    """Raise ScenarioError (dari simulasi.rules) jika parameter skenario tidak valid."""
    base_det = run_simulation(baseline)
    base_reps = run_replications(baseline, replications, seed)
    base_kpi = compute_kpis(base_det, base_det)
    base_rep_kpis = [compute_kpis(r, r) for r in base_reps]
    baseline_eval = _evaluation(None, "Baseline", base_det, base_kpi, base_rep_kpis, None)

    evaluations = []
    for scenario in scenarios:
        snap = apply_scenario(baseline, scenario.parameters)
        det = run_simulation(snap)
        # Replikasi ke-i skenario dibandingkan dengan replikasi ke-i baseline
        # (angka acak per task sama, lihat engine.run_replications).
        reps = run_replications(snap, replications, seed)
        rep_kpis = [compute_kpis(r, ref) for r, ref in zip(reps, base_reps, strict=True)]
        evaluations.append(
            _evaluation(
                scenario.scenario_id,
                scenario.name,
                det,
                compute_kpis(det, base_det),
                rep_kpis,
                base_kpi,
            )
        )

    ranking = rank_scenarios(evaluations)
    return CompareResponse(
        data_source=baseline.data_source,
        replications=replications,
        baseline=baseline_eval,
        scenarios=evaluations,
        best_scenario_id=ranking[0] if ranking else None,
        ranking=ranking,
        ranking_basis=[KPI_BY_KEY[k].label for k in RANKING_ORDER],
    )
