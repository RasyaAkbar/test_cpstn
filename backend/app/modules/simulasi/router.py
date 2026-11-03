"""Endpoint modul simulasi: /api/v1/simulasi/...

PEMILIK: Orang 2 — Simulasi (Iterasi 1).

  GET    /baseline                    baseline untuk dropdown form           (UC-01)
  GET    /scenarios                   daftar skenario tersimpan              (UC-01)
  POST   /scenarios                   buat skenario                          (UC-01, FR-01)
  GET    /scenarios/{id}              detail skenario                        (UC-02)
  PUT    /scenarios/{id}              ubah parameter skenario                (UC-02, FR-02)
  DELETE /scenarios/{id}              hapus skenario
  POST   /scenarios/{id}/duplicate    duplikat skenario                      (UC-02, FR-02)
  POST   /scenarios/{id}/run          jalankan simulasi vs baseline          (UC-03/04, FR-03/04)
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.modules.simulasi.baseline import get_baseline_snapshot
from app.modules.simulasi.domain import Snapshot
from app.modules.simulasi.rules import ScenarioError, apply_scenario
from app.modules.simulasi.schemas import (
    BaselineResponse,
    Scenario,
    ScenarioInput,
    SimulationRunResponse,
)
from app.modules.simulasi.service import baseline_response, run_response, simulate_pair
from app.modules.simulasi.store import ScenarioStore, get_scenario_store

router = APIRouter(prefix="/simulasi", tags=["Simulasi"])

Baseline = Annotated[Snapshot, Depends(get_baseline_snapshot)]
Store = Annotated[ScenarioStore, Depends(get_scenario_store)]


def _found(scenario: Scenario | None) -> Scenario:
    if scenario is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Skenario tidak ditemukan")
    return scenario


def _validated(baseline: Snapshot, data: ScenarioInput) -> None:
    """Tolak skenario yang merujuk proyek/anggota/task yang tidak ada (422)."""
    try:
        apply_scenario(baseline, data.parameters)
    except ScenarioError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc


@router.get("/baseline", response_model=BaselineResponse)
def get_baseline(baseline: Baseline) -> BaselineResponse:
    return baseline_response(baseline)


@router.get("/scenarios", response_model=list[Scenario])
def list_scenarios(store: Store) -> list[Scenario]:
    return store.list()


@router.post("/scenarios", response_model=Scenario, status_code=status.HTTP_201_CREATED)
def create_scenario(data: ScenarioInput, baseline: Baseline, store: Store) -> Scenario:
    _validated(baseline, data)
    return store.create(data, baseline.data_source)


@router.get("/scenarios/{scenario_id}", response_model=Scenario)
def get_scenario(scenario_id: str, store: Store) -> Scenario:
    return _found(store.get(scenario_id))


@router.put("/scenarios/{scenario_id}", response_model=Scenario)
def update_scenario(
    scenario_id: str, data: ScenarioInput, baseline: Baseline, store: Store
) -> Scenario:
    _found(store.get(scenario_id))
    _validated(baseline, data)
    return _found(store.update(scenario_id, data))


@router.delete("/scenarios/{scenario_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_scenario(scenario_id: str, store: Store) -> Response:
    if not store.delete(scenario_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Skenario tidak ditemukan")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/scenarios/{scenario_id}/duplicate",
    response_model=Scenario,
    status_code=status.HTTP_201_CREATED,
)
def duplicate_scenario(scenario_id: str, store: Store) -> Scenario:
    return _found(store.duplicate(scenario_id))


@router.post("/scenarios/{scenario_id}/run", response_model=SimulationRunResponse)
def run_scenario(scenario_id: str, baseline: Baseline, store: Store) -> SimulationRunResponse:
    scenario = _found(store.get(scenario_id))
    try:
        base, scen = simulate_pair(baseline, scenario)
    except ScenarioError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    return run_response(scenario, base, scen)
