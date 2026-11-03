"""Kontrak API modul evaluasi: KPI dan perbandingan baseline vs skenario.

PEMILIK: Orang 3 — KPI (Iterasi 2, FR-05/FR-06).
Tipe TypeScript padanannya ada di frontend/src/modules/evaluasi/api.ts (Orang 1).
"""

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field


class KpiDefinitionOut(BaseModel):
    key: str
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
    value: float  # run deterministik (effort = estimated_days)
    distribution: Distribution | None = None  # hanya jika replications > 0
    delta: float | None = None  # skenario − baseline; None untuk baseline
    status: Literal["better", "worse", "same"] | None = None


class ProjectKpiOut(BaseModel):
    project_id: str
    project_name: str
    target_launch_date: date
    projected_finish: date | None
    delay_days: int
    on_target: bool
    on_target_probability: float | None = None  # porsi replikasi yang tepat waktu (0..1)


class MemberLoadOut(BaseModel):
    resource_id: str
    resource_name: str
    demand_days: float
    capacity_days: float
    load_pct: float
    overloaded: bool


class Evaluation(BaseModel):
    scenario_id: str | None  # None = baseline
    name: str
    kpis: list[KpiValue]
    projects: list[ProjectKpiOut]
    members: list[MemberLoadOut]
    warnings: list[str]


class CompareRequest(BaseModel):
    scenario_ids: list[str] = Field(min_length=1, max_length=5)
    replications: int = Field(default=0, ge=0, le=1000)  # 0 = hanya run deterministik
    seed: int = 42


class CompareResponse(BaseModel):
    data_source: str
    replications: int
    baseline: Evaluation
    scenarios: list[Evaluation]
    best_scenario_id: str | None
    ranking: list[str]  # scenario_id dari terbaik ke terburuk
    ranking_basis: list[str]  # label KPI yang dipakai, sesuai urutan prioritas
