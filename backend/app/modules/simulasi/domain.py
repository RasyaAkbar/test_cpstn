"""Model data baseline (snapshot) yang dibaca mesin simulasi.

PEMILIK: Orang 2 — Simulasi (Iterasi 1).

Nama kolom mengikuti Tabel 4.3 (projects.csv, resources.csv, roles.csv, ...).
Hanya kolom yang dipakai simulasi yang dimuat. Field yang ditandai "[sim]" bukan
kolom CSV PuTI; field itu diisi oleh aturan skenario (lihat rules.py).

Semua dataclass frozen: skenario tidak pernah mengubah baseline, tetapi membuat
salinan baru dengan dataclasses.replace (desain IV.2.3: "takes a copy of the baseline").
"""

from dataclasses import dataclass
from datetime import date
from functools import cached_property


@dataclass(frozen=True)
class Project:  # projects.csv
    project_id: str
    project_name: str
    priority_rank: int  # 1 = prioritas tertinggi
    start_date: date
    target_launch_date: date


@dataclass(frozen=True)
class Role:  # roles.csv
    role_id: str
    role_name: str
    # Hari-orang kerja proyek per hari kerja (0..1). Sisa hari dipakai operasional
    # rutin, sesuai tiga jenis aktivitas yang dilaporkan PuTI (Tabel 1.1).
    capacity_reference: float


@dataclass(frozen=True)
class Resource:  # resources.csv
    resource_id: str
    resource_name: str
    primary_role_id: str
    secondary_role_ids: tuple[str, ...] = ()
    cross_role_capable: bool = False
    join_date: date | None = None
    seniority: str = "mid"
    onboarding_days: int = 0  # [sim] hari kerja ramp-up anggota baru
    initial_capacity: float = 1.0  # [sim] faktor kapasitas di hari pertama onboarding
    leave_date: date | None = None  # [sim] tanggal keluar dari unit (withdrawal)


@dataclass(frozen=True)
class ComplexityLevel:  # complexity_levels.csv
    complexity_id: str
    complexity_name: str
    min_days: float
    max_days: float
    load_weight: float  # belum dipakai di Iterasi 1–2; dimuat agar kontrak data lengkap


@dataclass(frozen=True)
class Task:  # tasks.csv
    task_id: str
    project_id: str
    task_name: str
    required_role_id: str
    complexity_id: str
    priority_rank: int
    estimated_days: float  # effort dalam hari-orang pada kapasitas penuh
    phase: str = ""
    status: str = "todo"  # todo | in_progress | done
    earliest_start: date | None = None  # [sim] task CR tidak bisa mulai sebelum tanggal CR


@dataclass(frozen=True)
class Dependency:  # task_dependencies.csv
    task_id: str
    depends_on_task_id: str
    dependency_type: str = "FS"
    # Porsi predecessor yang harus selesai sebelum task boleh mulai (0..1).
    # 1.0 = finish-to-start penuh: keterlambatan predecessor diteruskan seluruhnya.
    # 0.5 = task boleh mulai saat predecessor 50% selesai. Asumsi ini perlu
    # dikonfirmasi ke PuTI (desain IV.2.3 langkah 4).
    propagation_factor: float = 1.0


@dataclass(frozen=True)
class Assignment:  # assignments.csv
    task_id: str
    resource_id: str
    assigned_date: date | None = None  # None = sejak awal
    released_date: date | None = None  # None = sampai task selesai


@dataclass(frozen=True)
class Availability:  # availability.csv (cuti / absen)
    resource_id: str
    date_start: date
    date_end: date  # inklusif
    absence_type: str = "planned"


@dataclass(frozen=True)
class Holiday:  # holidays.csv
    holiday_date: date
    holiday_name: str


@dataclass(frozen=True)
class WorkloadItem:  # workload_items.csv (tiket, operasional, hotfix)
    item_id: str
    resource_id: str
    item_type: str
    related_project_id: str | None
    received_date: date
    # [sim] Di data PuTI effort diturunkan dari started_date → resolved_date.
    effort_days: float
    severity: str = "normal"
    is_hotfix: bool = False


@dataclass(frozen=True)
class Block:  # [sim] dari skenario task blocker
    task_id: str
    date_start: date
    working_days: int


@dataclass(frozen=True)
class Mentorship:  # [sim] dari skenario anggota baru
    mentor_id: str
    mentee_id: str
    overhead: float  # porsi hari mentor yang terpakai selama mentee onboarding


@dataclass(frozen=True)
class Snapshot:
    """Baseline lengkap yang disimulasikan (langkah 1 desain IV.2.3)."""

    start_date: date  # hari ke-0 simulasi
    data_source: str  # "synthetic" atau "puti"; ditampilkan di setiap layar
    projects: tuple[Project, ...]
    roles: tuple[Role, ...]
    resources: tuple[Resource, ...]
    complexity_levels: tuple[ComplexityLevel, ...]
    tasks: tuple[Task, ...]
    dependencies: tuple[Dependency, ...] = ()
    assignments: tuple[Assignment, ...] = ()
    availability: tuple[Availability, ...] = ()
    holidays: tuple[Holiday, ...] = ()
    workload_items: tuple[WorkloadItem, ...] = ()
    blocks: tuple[Block, ...] = ()
    mentorships: tuple[Mentorship, ...] = ()
    removed_task_ids: tuple[str, ...] = ()  # task yang di-drop skenario (dipakai KPI)

    # Indeks pencarian. cached_property aman pada dataclass frozen tanpa slots.
    @cached_property
    def project_by_id(self) -> dict[str, Project]:
        return {p.project_id: p for p in self.projects}

    @cached_property
    def role_by_id(self) -> dict[str, Role]:
        return {r.role_id: r for r in self.roles}

    @cached_property
    def resource_by_id(self) -> dict[str, Resource]:
        return {r.resource_id: r for r in self.resources}

    @cached_property
    def complexity_by_id(self) -> dict[str, ComplexityLevel]:
        return {c.complexity_id: c for c in self.complexity_levels}

    @cached_property
    def task_by_id(self) -> dict[str, Task]:
        return {t.task_id: t for t in self.tasks}

    def open_tasks(self) -> list[Task]:
        """Task yang masih harus dikerjakan (belum selesai)."""
        return [t for t in self.tasks if t.status != "done"]
