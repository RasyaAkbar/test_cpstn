"""Endpoint modul evaluasi: /api/v1/evaluasi/...

PEMILIK: Orang 3 — KPI (Iterasi 2).

  GET  /kpi-definitions   daftar KPI, nomor FR, satuan, dan arah "lebih baik"   (FR-05)
  POST /compare           KPI baseline vs skenario + skenario terbaik           (UC-05/UC-06, FR-06)
  GET  /historical        EAR dan Rework Rate dari data aktual                  (FR-04.8, FR-04.9)

Skenario dan baseline dibaca dari modul simulasi (Orang 2) lewat dependency yang sama.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.modules.evaluasi.comparison import compare
from app.modules.evaluasi.historical import historical_kpis
from app.modules.evaluasi.kpi import KPI_DEFINITIONS
from app.modules.evaluasi.schemas import (
    CompareRequest,
    CompareResponse,
    HistoricalResponse,
    KpiDefinitionOut,
)
from app.modules.simulasi.baseline import get_baseline_snapshot
from app.modules.simulasi.domain import Snapshot
from app.modules.simulasi.rules import ScenarioError
from app.modules.simulasi.store import ScenarioStore, get_scenario_store

router = APIRouter(prefix="/evaluasi", tags=["Evaluasi"])

Baseline = Annotated[Snapshot, Depends(get_baseline_snapshot)]


@router.get("/kpi-definitions", response_model=list[KpiDefinitionOut])
def kpi_definitions() -> list[KpiDefinitionOut]:
    return [KpiDefinitionOut(**vars(k)) for k in KPI_DEFINITIONS]


@router.post("/compare", response_model=CompareResponse)
def compare_scenarios(
    request: CompareRequest,
    baseline: Baseline,
    store: Annotated[ScenarioStore, Depends(get_scenario_store)],
) -> CompareResponse:
    scenarios = []
    for scenario_id in dict.fromkeys(request.scenario_ids):  # buang duplikat, jaga urutan
        scenario = store.get(scenario_id)
        if scenario is None:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, f"Skenario {scenario_id} tidak ditemukan"
            )
        scenarios.append(scenario)
    try:
        return compare(
            baseline, scenarios, request.replications, request.seed, request.overload_threshold
        )
    except ScenarioError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc


@router.get("/historical", response_model=HistoricalResponse)
def historical(baseline: Baseline) -> HistoricalResponse:
    result = historical_kpis(baseline)
    return HistoricalResponse(
        data_source=baseline.data_source,
        as_of=baseline.as_of,
        notes=list(baseline.notes),
        **{
            key: [vars(g) for g in value] if isinstance(value, list) else value
            for key, value in vars(result).items()
        },
    )
