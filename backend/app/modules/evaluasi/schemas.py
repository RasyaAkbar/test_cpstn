"""Kontrak API modul evaluasi: KPI dan perbandingan baseline vs skenario.

PEMILIK: Orang 3 — KPI (Iterasi 2, FR-05/FR-06).
Tipe TypeScript padanannya ada di frontend/src/modules/evaluasi/api.ts (Orang 1).
"""

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field


class KpiDefinitionOut(BaseModel):
    key: str
    fr: str
    label: str
    unit: str
    better: Literal["lower", "higher"]
    description: str


class Distribution(BaseModel):
    """Sebaran nilai KPI dari replikasi Monte Carlo (desain IV.2.3)."""

    median: float
    p10: float
    p90: float


class KpiValue(BaseModel):
    key: str
    # Run deterministik (effort = sisa estimasi). on_time_probability berasal dari
    # replikasi; None jika replications = 0 atau KPI tidak terdefinisi.
    value: float | None
    distribution: Distribution | None = None  # hanya jika replications > 0
    delta: float | None = None  # skenario − baseline; None untuk baseline
    status: Literal["better", "worse", "same"] | None = None


class ProjectKpiOut(BaseModel):
    project_id: str
    project_name: str
    target_launch_date: date
    projected_finish: date | None
    sv_days: int  # Schedule Variance (hari kerja); positif = terlambat
    on_target: bool
    on_target_probability: float | None = None  # porsi replikasi dengan SV ≤ 0 (0..1)


class ResourceKpiOut(BaseModel):
    resource_id: str
    resource_name: str
    role_id: str
    weekly_rli: list[float | None]  # sejajar dengan Evaluation.week_starts
    rli_peak: float
    rli_mean: float
    overload_weeks: int
    soi: float
    blocked_ratio: float | None
    reallocated_ratio: float | None


class TaskCascadeOut(BaseModel):
    task_id: str
    task_name: str
    project_id: str
    delay_days: int
    downstream_tasks: int
    cdi: float


class Evaluation(BaseModel):
    scenario_id: str | None  # None = baseline
    name: str
    kpis: list[KpiValue]
    projects: list[ProjectKpiOut]
    members: list[ResourceKpiOut]
    cascade: list[TaskCascadeOut]  # task dengan CDI terbesar (FR-04.7)
    week_starts: list[date]
    warnings: list[str]


class CompareRequest(BaseModel):
    scenario_ids: list[str] = Field(min_length=1, max_length=5)
    # FR-04.2: bawaan 100 replikasi per skenario. 0 = hanya run deterministik.
    replications: int = Field(default=100, ge=0, le=1000)
    seed: int = 42
    overload_threshold: float = Field(default=1.0, gt=0, le=10)  # FR-04.4 / FR-04.11


class CompareResponse(BaseModel):
    data_source: str
    replications: int
    overload_threshold: float
    baseline: Evaluation
    scenarios: list[Evaluation]
    best_scenario_id: str | None
    ranking: list[str]  # scenario_id dari terbaik ke terburuk
    ranking_basis: list[str]  # label KPI yang dipakai, sesuai urutan prioritas


class GroupRatioOut(BaseModel):
    key: str
    label: str
    value: float | None
    tasks: int


class HistoricalResponse(BaseModel):
    """KPI dari data aktual (FR-04.8, FR-04.9); tidak bergantung pada skenario."""

    data_source: str
    as_of: date | None
    notes: list[str]  # cara data disiapkan untuk simulasi (db_baseline.py)
    ear: float | None
    ear_by_complexity: list[GroupRatioOut]
    ear_by_role: list[GroupRatioOut]
    rework_rate: float | None  # %
    rework_by_role: list[GroupRatioOut]
    rework_by_project: list[GroupRatioOut]
