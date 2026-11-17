"""Kontrak API modul simulasi: parameter skenario dan respons hasil simulasi.

PEMILIK: Orang 2 — Simulasi (Iterasi 1, FR-01 s.d. FR-04).
Tipe TypeScript padanannya ada di frontend/src/modules/simulasi/api.ts (Orang 1);
ubah keduanya bersamaan.

Satu kelas parameter per situasi keputusan di Tabel 4.2 / 4.4. Field `situation`
menjadi discriminator sehingga FastAPI memvalidasi parameter sesuai situasinya.
"""

from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field, model_validator

Situation = Literal[
    "change_request",
    "member_absence",
    "new_member",
    "rotation",
    "task_overrun",
    "task_blocker",
    "priority_change",
    "critical_bug",
]


# ─── FR-01/FR-02: parameter skenario per situasi (Tabel 4.4) ────────────────────


class NewTask(BaseModel):
    task_name: str = Field(min_length=1, max_length=120)
    required_role_id: str
    complexity_id: str
    estimated_days: float = Field(gt=0, le=200)
    assignee_id: str | None = None  # None = pilih otomatis anggota role sama yang paling longgar
    depends_on_task_ids: list[str] = []
    priority_rank: int = Field(default=99, ge=1)


class ChangeRequestParams(BaseModel):
    """Mid-sprint CR: tambah dan/atau hapus task pada satu proyek."""

    situation: Literal["change_request"] = "change_request"
    project_id: str
    request_date: date
    add_tasks: list[NewTask] = []
    remove_task_ids: list[str] = []

    @model_validator(mode="after")
    def _has_change(self):
        if not self.add_tasks and not self.remove_task_ids:
            raise ValueError("CR harus menambah atau menghapus minimal satu task")
        return self


class MemberAbsenceParams(BaseModel):
    """Anggota tidak hadir; opsional ada pengganti dengan role sama."""

    situation: Literal["member_absence"] = "member_absence"
    resource_id: str
    date_start: date
    date_end: date
    absence_type: Literal["planned", "sudden"] = "sudden"
    cover_resource_id: str | None = None
    auto_cover: bool = False  # True = sistem memilih pengganti role sama yang paling longgar

    @model_validator(mode="after")
    def _date_order(self):
        if self.date_end < self.date_start:
            raise ValueError("date_end tidak boleh sebelum date_start")
        return self


class NewMemberParams(BaseModel):
    """Anggota baru bergabung dengan masa onboarding (Brooks, 1995)."""

    situation: Literal["new_member"] = "new_member"
    resource_name: str = Field(min_length=1, max_length=80)
    role_id: str
    seniority: Literal["junior", "mid", "senior"] = "junior"
    join_date: date
    onboarding_days: int = Field(default=10, ge=0, le=60)  # PuTI: 1–2 minggu
    initial_capacity: float = Field(default=0.3, ge=0, le=1)
    mentor_resource_id: str | None = None
    mentor_overhead: float = Field(default=0.1, ge=0, le=0.5)
    project_id: str | None = None  # bantu semua task role sama di proyek ini
    assist_task_ids: list[str] = []  # atau pilih task tertentu


class RotationParams(BaseModel):
    """Rotasi anggota ke proyek lain, atau keluar dari unit jika to_project_id kosong."""

    situation: Literal["rotation"] = "rotation"
    resource_id: str
    transfer_date: date
    from_project_id: str
    to_project_id: str | None = None
    replacement_resource_id: str | None = None
    auto_replacement: bool = True


class TaskOverrunParams(BaseModel):
    situation: Literal["task_overrun"] = "task_overrun"
    task_id: str
    revised_estimated_days: float = Field(gt=0, le=200)


class TaskBlockerParams(BaseModel):
    situation: Literal["task_blocker"] = "task_blocker"
    task_id: str
    block_start: date
    block_days: int = Field(ge=1, le=120)  # hari kerja


class TaskPriority(BaseModel):
    task_id: str
    priority_rank: int = Field(ge=1)


class PriorityChangeParams(BaseModel):
    situation: Literal["priority_change"] = "priority_change"
    project_id: str
    new_priority_rank: int | None = Field(default=None, ge=1)
    task_priorities: list[TaskPriority] = []
    new_target_launch_date: date | None = None

    @model_validator(mode="after")
    def _has_change(self):
        if (
            self.new_priority_rank is None
            and not self.task_priorities
            and self.new_target_launch_date is None
        ):
            raise ValueError("Isi minimal satu perubahan prioritas atau target")
        return self


class CriticalBugParams(BaseModel):
    """Hotfix yang mendahului pekerjaan fitur anggota yang ditugaskan."""

    situation: Literal["critical_bug"] = "critical_bug"
    resource_id: str
    report_date: date
    fix_days: float = Field(gt=0, le=60)
    severity: Literal["critical", "high"] = "critical"
    related_project_id: str | None = None


ScenarioParameters = Annotated[
    ChangeRequestParams
    | MemberAbsenceParams
    | NewMemberParams
    | RotationParams
    | TaskOverrunParams
    | TaskBlockerParams
    | PriorityChangeParams
    | CriticalBugParams,
    Field(discriminator="situation"),
]


class ScenarioInput(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=500)
    parameters: ScenarioParameters


class Scenario(ScenarioInput):
    scenario_id: str
    data_source: str
    created_at: datetime
    updated_at: datetime


# ─── Baseline untuk form skenario (dropdown di frontend) ────────────────────────


class BaselineProject(BaseModel):
    project_id: str
    project_name: str
    priority_rank: int
    start_date: date
    target_launch_date: date


class BaselineResource(BaseModel):
    resource_id: str
    resource_name: str
    primary_role_id: str
    secondary_role_ids: list[str]


class BaselineTask(BaseModel):
    task_id: str
    project_id: str
    task_name: str
    required_role_id: str
    complexity_id: str
    estimated_days: float
    status: str
    assignee_ids: list[str]


class Option(BaseModel):
    id: str
    name: str


class BaselineResponse(BaseModel):
    data_source: str
    start_date: date
    as_of: date | None = None  # tanggal observasi terakhir di dataset
    notes: list[str] = []  # cara data disiapkan untuk simulasi (asumsi yang perlu dicek)
    projects: list[BaselineProject]
    resources: list[BaselineResource]
    tasks: list[BaselineTask]
    roles: list[Option]
    complexity_levels: list[Option]


# ─── FR-04: hasil simulasi (baseline vs skenario) ───────────────────────────────


class ProjectOutcome(BaseModel):
    project_id: str
    project_name: str
    target_launch_date: date
    baseline_finish: date | None
    scenario_finish: date | None
    shift_days: int | None  # skenario − baseline (hari kalender); + berarti mundur


class TaskChange(BaseModel):
    task_id: str
    project_id: str
    task_name: str
    change: Literal["added", "removed", "shifted", "unchanged"]
    baseline_start: date | None
    baseline_finish: date | None
    scenario_start: date | None
    scenario_finish: date | None
    shift_days: int | None


class WeeklyLoad(BaseModel):
    week_start: date
    capacity: float  # hari-orang tersedia
    used: float  # hari-orang terpakai (proyek + tiket)


class ResourceLoad(BaseModel):
    resource_id: str
    resource_name: str
    baseline: list[WeeklyLoad]
    scenario: list[WeeklyLoad]


class SimulationRunResponse(BaseModel):
    scenario: Scenario
    data_source: str
    projects: list[ProjectOutcome]
    tasks: list[TaskChange]
    resource_load: list[ResourceLoad]
    warnings: list[str]
