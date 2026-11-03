"""Endpoint modul evaluasi: /api/v1/evaluasi/...

PEMILIK: Orang 3 — KPI (Iterasi 2).

  GET  /kpi-definitions   daftar KPI, satuan, dan arah "lebih baik"     (FR-05)
  POST /compare           KPI baseline vs skenario + skenario terbaik   (UC-05/UC-06, FR-06)

Skenario dan baseline dibaca dari modul simulasi (Orang 2) lewat dependency yang sama.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.modules.evaluasi.comparison import compare
from app.modules.evaluasi.kpi import KPI_DEFINITIONS
from app.modules.evaluasi.schemas import CompareRequest, CompareResponse, KpiDefinitionOut
from app.modules.simulasi.baseline import get_baseline_snapshot
from app.modules.simulasi.domain import Snapshot
from app.modules.simulasi.rules import ScenarioError
from app.modules.simulasi.store import ScenarioStore, get_scenario_store

router = APIRouter(prefix="/evaluasi", tags=["Evaluasi"])


@router.get("/kpi-definitions", response_model=list[KpiDefinitionOut])
def kpi_definitions() -> list[KpiDefinitionOut]:
    return [KpiDefinitionOut(**vars(k)) for k in KPI_DEFINITIONS]


@router.post("/compare", response_model=CompareResponse)
def compare_scenarios(
    request: CompareRequest,
    baseline: Annotated[Snapshot, Depends(get_baseline_snapshot)],
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
        return compare(baseline, scenarios, request.replications, request.seed)
    except ScenarioError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
