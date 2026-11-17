"""Tabel dataset baseline PuTI (Tabel 4.3) di PostgreSQL.

Setiap tabel mencerminkan satu sheet di puti_datasets.xlsx (sheet `<tabel>_csv`): nama
tabel, nama kolom, dan urutan kolom sama persis dengan file tersebut.

Aturan kualitas data (ISO/IEC 25012, III.1.2) ditulis sekali di sini sebagai CHECK
constraint: nilai yang diizinkan, urutan tanggal, dan rentang angka. Setiap constraint
membawa `info` yang dibaca importer (importer.py), sehingga pengguna mendapat pesan galat
per baris Excel sebelum data menyentuh database, dan database tetap menolak data yang lolos
dari jalur lain.
"""

from datetime import date, datetime

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Table,
    Text,
    TypeDecorator,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# ─── Nilai yang diizinkan (sesuai isi puti_datasets.xlsx) ───

DATA_SOURCES = ("synthetic", "puti")
PROJECT_STATUSES = ("development", "testing", "released")
SENIORITY_LEVELS = ("junior", "mid", "senior")
TASK_PHASES = (
    "planning",
    "uiux",
    "fe_dev",
    "be_dev",
    "dm_dev",
    "testing",
    "bugfix",
    "documentation",
)
TASK_STATUSES = (
    "not_started",
    "in_progress",
    "in_qa",
    "blocked",
    "on_hold",
    "done",
    "dropped",
)
DEPENDENCY_TYPES = ("hard", "soft")
WORKLOAD_ITEM_TYPES = ("ticket", "operational")
SEVERITIES = ("low", "medium", "high", "critical")
ABSENCE_TYPES = (
    "planned_leave",
    "sudden_leave",
    "maternity_leave",
    "rotation_in",
    "rotation_out",
)
EVENT_TYPES = ("change_request", "blocker", "overrun", "hotfix", "priority_change")
DECISIONS = ("accept_now", "defer_next", "reject")
RESOLUTION_MODES = ("scope_addition", "extend_duration", "swap_task", "reshuffle")


# ─── Tipe kolom dan pembuat constraint ───


def _id() -> String:
    return String(20)


def _days() -> Numeric:
    """Angka hari/faktor dengan maksimal 2 desimal, dibaca sebagai float di Python."""
    return Numeric(6, 2, asdecimal=False)


class SemicolonList(TypeDecorator):
    """Daftar ID dalam satu sel, dipisah titik koma ("ROLE-TW;ROLE-SA"), seperti di Excel.

    Database menyimpan teks yang sama persis dengan sel Excel (NULL jika kosong); Python
    melihatnya sebagai list[str].
    """

    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if not value:
            return None
        return ";".join(value)

    def process_result_value(self, value, dialect):
        if not value:
            return []
        return [part for part in value.split(";") if part]


def one_of(column: str, values: tuple[str, ...]) -> CheckConstraint:
    allowed = ", ".join(f"'{value}'" for value in values)
    return CheckConstraint(
        f"{column} IN ({allowed})",
        name=f"{column}_allowed",
        info={"one_of": (column, values)},
    )


def ordered(first: str, second: str) -> CheckConstraint:
    """`second` tidak boleh lebih kecil/awal dari `first` (NULL selalu lolos)."""
    return CheckConstraint(
        f"{second} >= {first}",
        name=f"{second}_gte_{first}",
        info={"ordered": (first, second)},
    )


def in_range(
    column: str,
    minimum: float | None = None,
    maximum: float | None = None,
    *,
    exclusive_minimum: bool = False,
) -> CheckConstraint:
    parts = []
    if minimum is not None:
        parts.append(f"{column} {'>' if exclusive_minimum else '>='} {minimum}")
    if maximum is not None:
        parts.append(f"{column} <= {maximum}")
    return CheckConstraint(
        " AND ".join(parts),
        name=f"{column}_range",
        info={"in_range": (column, minimum, maximum, exclusive_minimum)},
    )


def distinct(first: str, second: str) -> CheckConstraint:
    return CheckConstraint(
        f"{first} <> {second}",
        name=f"{first}_not_{second}",
        info={"distinct": (first, second)},
    )


# ─── Tabel dataset (urutan kolom = urutan kolom di Excel) ───


class Role(Base):  # roles_csv
    __tablename__ = "roles"
    __table_args__ = (in_range("capacity_reference", 0, exclusive_minimum=True),)

    role_id: Mapped[str] = mapped_column(_id(), primary_key=True)
    role_name: Mapped[str] = mapped_column(String(120))
    capacity_reference: Mapped[float] = mapped_column(_days())
    description: Mapped[str | None] = mapped_column(Text)


class ComplexityLevel(Base):  # complexity_levels_csv
    __tablename__ = "complexity_levels"
    __table_args__ = (
        in_range("min_days", 0, exclusive_minimum=True),
        ordered("min_days", "max_days"),
        in_range("load_weight", 0, exclusive_minimum=True),
    )

    complexity_id: Mapped[str] = mapped_column(_id(), primary_key=True)
    complexity_name: Mapped[str] = mapped_column(String(60))
    min_days: Mapped[float] = mapped_column(_days())
    max_days: Mapped[float] = mapped_column(_days())
    load_weight: Mapped[float] = mapped_column(_days())


class Project(Base):  # projects_csv
    __tablename__ = "projects"
    __table_args__ = (
        in_range("priority_rank", 1),
        ordered("start_date", "target_launch_date"),
        ordered("start_date", "actual_launch_date"),
        one_of("status", PROJECT_STATUSES),
    )

    project_id: Mapped[str] = mapped_column(_id(), primary_key=True)
    project_name: Mapped[str] = mapped_column(String(200))
    process_owner: Mapped[str] = mapped_column(String(120))
    priority_rank: Mapped[int] = mapped_column(Integer)
    start_date: Mapped[date] = mapped_column(Date)
    target_launch_date: Mapped[date] = mapped_column(Date)
    actual_launch_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20))
    dor_fulfilled: Mapped[bool]


class Resource(Base):  # resources_csv
    __tablename__ = "resources"
    __table_args__ = (one_of("seniority", SENIORITY_LEVELS),)

    resource_id: Mapped[str] = mapped_column(_id(), primary_key=True)
    resource_name: Mapped[str] = mapped_column(String(100))
    primary_role_id: Mapped[str] = mapped_column(_id(), ForeignKey("roles.role_id"), index=True)
    secondary_role_ids: Mapped[list[str]] = mapped_column(
        SemicolonList(), nullable=True, info={"references_each": "roles.role_id"}
    )
    cross_role_capable: Mapped[bool]
    join_date: Mapped[date] = mapped_column(Date)
    seniority: Mapped[str] = mapped_column(String(10))


class Task(Base):  # tasks_csv
    __tablename__ = "tasks"
    __table_args__ = (
        in_range("priority_rank", 1),
        in_range("estimated_days", 0, exclusive_minimum=True),
        one_of("phase", TASK_PHASES),
        ordered("planned_start", "planned_finish"),
        ordered("actual_start", "actual_finish"),
        one_of("status", TASK_STATUSES),
        in_range("qa_reject_count", 0),
    )

    task_id: Mapped[str] = mapped_column(_id(), primary_key=True)
    project_id: Mapped[str] = mapped_column(_id(), ForeignKey("projects.project_id"), index=True)
    feature_name: Mapped[str] = mapped_column(String(120))
    task_name: Mapped[str] = mapped_column(String(200))
    required_role_id: Mapped[str] = mapped_column(_id(), ForeignKey("roles.role_id"), index=True)
    complexity_id: Mapped[str] = mapped_column(_id(), ForeignKey("complexity_levels.complexity_id"))
    priority_rank: Mapped[int] = mapped_column(Integer)
    estimated_days: Mapped[float] = mapped_column(_days())
    phase: Mapped[str] = mapped_column(String(20))
    planned_start: Mapped[date] = mapped_column(Date)
    planned_finish: Mapped[date] = mapped_column(Date)
    actual_start: Mapped[date | None] = mapped_column(Date)
    actual_finish: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20))
    qa_reject_count: Mapped[int] = mapped_column(Integer)
    dod_fulfilled: Mapped[bool]


class TaskDependency(Base):  # task_dependencies_csv
    __tablename__ = "task_dependencies"
    __table_args__ = (
        UniqueConstraint("task_id", "depends_on_task_id"),
        distinct("task_id", "depends_on_task_id"),
        one_of("dependency_type", DEPENDENCY_TYPES),
        in_range("propagation_factor", 0, 1),
    )

    dependency_id: Mapped[str] = mapped_column(_id(), primary_key=True)
    task_id: Mapped[str] = mapped_column(_id(), ForeignKey("tasks.task_id"), index=True)
    depends_on_task_id: Mapped[str] = mapped_column(_id(), ForeignKey("tasks.task_id"), index=True)
    dependency_type: Mapped[str] = mapped_column(String(10))
    propagation_factor: Mapped[float] = mapped_column(_days())


class Assignment(Base):  # assignments_csv
    __tablename__ = "assignments"
    __table_args__ = (ordered("assigned_date", "released_date"),)

    assignment_id: Mapped[str] = mapped_column(_id(), primary_key=True)
    task_id: Mapped[str] = mapped_column(_id(), ForeignKey("tasks.task_id"), index=True)
    resource_id: Mapped[str] = mapped_column(_id(), ForeignKey("resources.resource_id"), index=True)
    role_in_task: Mapped[str] = mapped_column(_id(), ForeignKey("roles.role_id"))
    assigned_date: Mapped[date] = mapped_column(Date)
    released_date: Mapped[date | None] = mapped_column(Date)
    is_takeover: Mapped[bool]


class WorkloadItem(Base):  # workload_items_csv
    __tablename__ = "workload_items"
    __table_args__ = (
        one_of("item_type", WORKLOAD_ITEM_TYPES),
        ordered("received_date", "started_date"),
        ordered("started_date", "resolved_date"),
        one_of("severity", SEVERITIES),
    )

    item_id: Mapped[str] = mapped_column(_id(), primary_key=True)
    resource_id: Mapped[str] = mapped_column(_id(), ForeignKey("resources.resource_id"), index=True)
    item_type: Mapped[str] = mapped_column(String(20))
    related_project_id: Mapped[str | None] = mapped_column(
        _id(), ForeignKey("projects.project_id"), index=True
    )
    received_date: Mapped[date] = mapped_column(Date)
    started_date: Mapped[date | None] = mapped_column(Date)
    resolved_date: Mapped[date | None] = mapped_column(Date)
    severity: Mapped[str] = mapped_column(String(10))
    is_hotfix: Mapped[bool]


class Availability(Base):  # availability_csv
    __tablename__ = "availability"
    __table_args__ = (
        ordered("date_start", "date_end"),
        one_of("absence_type", ABSENCE_TYPES),
    )

    availability_id: Mapped[str] = mapped_column(_id(), primary_key=True)
    resource_id: Mapped[str] = mapped_column(_id(), ForeignKey("resources.resource_id"), index=True)
    date_start: Mapped[date] = mapped_column(Date)
    date_end: Mapped[date] = mapped_column(Date)
    absence_type: Mapped[str] = mapped_column(String(20))
    is_known_at_planning: Mapped[bool]


class ChangeEvent(Base):  # change_events_csv
    __tablename__ = "change_events"
    __table_args__ = (
        one_of("event_type", EVENT_TYPES),
        one_of("decision", DECISIONS),
        one_of("resolution_mode", RESOLUTION_MODES),
        in_range("extension_days", 0),
    )

    event_id: Mapped[str] = mapped_column(_id(), primary_key=True)
    project_id: Mapped[str] = mapped_column(_id(), ForeignKey("projects.project_id"), index=True)
    event_type: Mapped[str] = mapped_column(String(20))
    event_date: Mapped[date] = mapped_column(Date)
    requested_by: Mapped[str] = mapped_column(String(60))
    decision: Mapped[str] = mapped_column(String(20))
    resolution_mode: Mapped[str] = mapped_column(String(20))
    affected_task_id: Mapped[str | None] = mapped_column(
        _id(), ForeignKey("tasks.task_id"), index=True
    )
    extension_days: Mapped[float] = mapped_column(_days())


class Holiday(Base):  # holidays_csv
    __tablename__ = "holidays"

    holiday_date: Mapped[date] = mapped_column(Date, primary_key=True)
    holiday_name: Mapped[str] = mapped_column(String(120))


# Urutan aman untuk insert (induk dulu); hapus dengan urutan terbalik.
DATASET_TABLES: tuple[Table, ...] = tuple(
    model.__table__
    for model in (
        Role,
        ComplexityLevel,
        Project,
        Resource,
        Task,
        TaskDependency,
        Assignment,
        WorkloadItem,
        Availability,
        ChangeEvent,
        Holiday,
    )
)


# ─── Riwayat import ───


class DatasetImport(Base):
    """Satu baris per import yang berhasil. Import terbaru = baseline yang sedang dimuat."""

    __tablename__ = "dataset_imports"
    __table_args__ = (one_of("data_source", DATA_SOURCES),)

    import_id: Mapped[int] = mapped_column(primary_key=True)
    source_file: Mapped[str] = mapped_column(String(255))
    file_sha256: Mapped[str] = mapped_column(String(64))
    data_source: Mapped[str] = mapped_column(String(20))
    row_counts: Mapped[dict[str, int]] = mapped_column(JSON)
    imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
