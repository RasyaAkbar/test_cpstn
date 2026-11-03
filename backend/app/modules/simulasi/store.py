"""Penyimpanan skenario: simpan, ubah, hapus, duplikat (Scenario Manager, FR-01/FR-02).

PEMILIK: Orang 2 — Simulasi (Iterasi 1).

Iterasi 1 menyimpan skenario di memori proses agar modul bisa diuji tanpa PostgreSQL.
Skenario hilang saat server restart. Untuk menyimpan permanen, buat model SQLAlchemy
+ migrasi Alembic dengan method yang sama, lalu ganti get_scenario_store().
"""

from datetime import UTC, datetime
from threading import Lock

from app.modules.simulasi.schemas import Scenario, ScenarioInput


class ScenarioStore:
    def __init__(self) -> None:
        self._items: dict[str, Scenario] = {}
        self._counter = 0
        self._lock = Lock()

    def list(self) -> list[Scenario]:
        return sorted(self._items.values(), key=lambda s: s.created_at)

    def get(self, scenario_id: str) -> Scenario | None:
        return self._items.get(scenario_id)

    def create(self, data: ScenarioInput, data_source: str) -> Scenario:
        with self._lock:
            self._counter += 1
            now = datetime.now(UTC)
            scenario = Scenario(
                scenario_id=f"SCN-{self._counter:03d}",
                data_source=data_source,
                created_at=now,
                updated_at=now,
                **data.model_dump(),
            )
            self._items[scenario.scenario_id] = scenario
            return scenario

    def update(self, scenario_id: str, data: ScenarioInput) -> Scenario | None:
        with self._lock:
            current = self._items.get(scenario_id)
            if current is None:
                return None
            updated = Scenario(
                scenario_id=scenario_id,
                data_source=current.data_source,
                created_at=current.created_at,
                updated_at=datetime.now(UTC),
                **data.model_dump(),
            )
            self._items[scenario_id] = updated
            return updated

    def delete(self, scenario_id: str) -> bool:
        with self._lock:
            return self._items.pop(scenario_id, None) is not None

    def duplicate(self, scenario_id: str) -> Scenario | None:
        source = self.get(scenario_id)
        if source is None:
            return None
        copy = ScenarioInput(
            name=f"{source.name} (salinan)"[:120],
            description=source.description,
            parameters=source.parameters,
        )
        return self.create(copy, source.data_source)


_store = ScenarioStore()


def get_scenario_store() -> ScenarioStore:
    """Dependency FastAPI; tes menggantinya dengan store baru lewat dependency_overrides."""
    return _store
