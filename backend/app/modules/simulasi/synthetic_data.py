"""Data sintetis baseline selama data PuTI belum dirilis (Tabel 3.2, "Synthetic project data").

PEMILIK: Orang 2 — Simulasi (Iterasi 1).

Struktur mengikuti Tabel 4.3. Nama anggota dipseudonimkan (UU PDP No. 27/2022, III.1.2).
Angka di sini bukan data PuTI: hasil simulasi menunjukkan perilaku sistem, bukan prakiraan
proyek nyata (III.2.2). Ganti sumber ini lewat baseline.get_baseline_snapshot() saat modul
Data / Digital Twin sudah menyediakan baseline.
"""

from datetime import date

from app.modules.simulasi.domain import (
    Assignment,
    Availability,
    ComplexityLevel,
    Dependency,
    Holiday,
    Project,
    Resource,
    Role,
    Snapshot,
    Task,
    WorkloadItem,
)

START_DATE = date(2026, 11, 2)  # Senin

ROLES = (
    Role("SA", "System Analyst", 0.6),
    Role("UX", "UI/UX Designer", 0.8),
    Role("FE", "Front-end Developer", 0.8),
    Role("BE", "Back-end Developer", 0.8),
    Role("QA", "Quality Assurance", 0.8),
)

COMPLEXITY = (
    ComplexityLevel("LOW", "Rendah", 1, 3, 1.0),
    ComplexityLevel("MED", "Sedang", 3, 8, 1.5),
    ComplexityLevel("HIGH", "Tinggi", 8, 15, 2.0),
)

RESOURCES = (
    Resource("RES-01", "Analis A", "SA", seniority="senior"),
    Resource("RES-02", "Desainer A", "UX", ("FE",), cross_role_capable=True),
    Resource("RES-03", "Frontend A", "FE", seniority="senior"),
    Resource("RES-04", "Frontend B", "FE", ("QA",), cross_role_capable=True, seniority="junior"),
    Resource("RES-05", "Backend A", "BE", ("FE",), cross_role_capable=True, seniority="senior"),
    Resource("RES-06", "Backend B", "BE"),
    Resource("RES-07", "QA A", "QA"),
    Resource("RES-08", "QA B", "QA", seniority="junior"),
)

PROJECTS = (
    Project("PRJ-A", "Sistem Pengadaan", 1, date(2026, 10, 5), date(2027, 1, 8)),
    Project("PRJ-B", "Portal Kepegawaian", 2, date(2026, 11, 2), date(2027, 2, 3)),
    Project("PRJ-C", "Aplikasi Aset", 3, date(2026, 11, 16), date(2027, 2, 17)),
)

# Template alur kerja satu proyek: (nama, role, kompleksitas, hari, fase, [(idx_pred, faktor)]).
TEMPLATE = (
    ("Analisis kebutuhan", "SA", "MED", 5, "analysis", []),
    ("Desain UI", "UX", "MED", 6, "design", [(0, 1.0)]),
    ("API dan basis data", "BE", "HIGH", 12, "development", [(0, 1.0)]),
    ("Integrasi layanan", "BE", "MED", 7, "development", [(2, 1.0)]),
    ("Halaman utama", "FE", "HIGH", 10, "development", [(1, 1.0), (2, 0.5)]),
    ("Halaman laporan", "FE", "MED", 6, "development", [(1, 1.0)]),
    ("Pengujian fungsional", "QA", "MED", 6, "testing", [(3, 1.0), (4, 1.0), (5, 1.0)]),
    ("Perbaikan hasil QA", "BE", "LOW", 3, "testing", [(6, 1.0)]),
    ("UAT dan rilis", "QA", "LOW", 2, "release", [(7, 1.0)]),
)

# Skala effort dan pemilik role per proyek. Anggota RES-01/02/03/05/07 dipakai lintas
# proyek, sesuai kondisi PuTI ("people shared across projects").
PROJECT_SETUP = {
    "PRJ-A": (
        1.0,
        {"SA": "RES-01", "UX": "RES-02", "BE": "RES-05", "FE": "RES-03", "QA": "RES-07"},
    ),
    "PRJ-B": (
        1.1,
        {"SA": "RES-01", "UX": "RES-02", "BE": "RES-06", "FE": "RES-04", "QA": "RES-08"},
    ),
    "PRJ-C": (
        0.9,
        {"SA": "RES-01", "UX": "RES-02", "BE": "RES-05", "FE": "RES-03", "QA": "RES-07"},
    ),
}
DONE_IN_BASELINE = {"PRJ-A": {0, 1}}  # PRJ-A sudah berjalan: analisis dan desain selesai

HOLIDAYS = (
    Holiday(date(2026, 12, 24), "Cuti bersama Natal"),
    Holiday(date(2026, 12, 25), "Hari Raya Natal"),
    Holiday(date(2027, 1, 1), "Tahun Baru"),
)


def build_synthetic_snapshot() -> Snapshot:
    tasks: list[Task] = []
    dependencies: list[Dependency] = []
    assignments: list[Assignment] = []
    for project in PROJECTS:
        scale, owners = PROJECT_SETUP[project.project_id]
        prefix = project.project_id.removeprefix("PRJ-")
        for idx, (name, role, cx, days, phase, preds) in enumerate(TEMPLATE):
            task_id = f"T-{prefix}{idx + 1:02d}"
            status = "done" if idx in DONE_IN_BASELINE.get(project.project_id, ()) else "todo"
            tasks.append(
                Task(
                    task_id,
                    project.project_id,
                    name,
                    role,
                    cx,
                    idx + 1,
                    float(round(days * scale)),
                    phase,
                    status,
                )
            )
            assignments.append(Assignment(task_id, owners[role]))
            for pred_idx, factor in preds:
                dependencies.append(
                    Dependency(task_id, f"T-{prefix}{pred_idx + 1:02d}", propagation_factor=factor)
                )

    return Snapshot(
        start_date=START_DATE,
        data_source="synthetic",
        projects=PROJECTS,
        roles=ROLES,
        resources=RESOURCES,
        complexity_levels=COMPLEXITY,
        tasks=tuple(tasks),
        dependencies=tuple(dependencies),
        assignments=tuple(assignments),
        availability=(Availability("RES-06", date(2026, 12, 21), date(2026, 12, 31), "planned"),),
        holidays=HOLIDAYS,
        workload_items=(
            WorkloadItem("WL-01", "RES-05", "ticket", "PRJ-A", date(2026, 11, 10), 0.5),
            WorkloadItem("WL-02", "RES-03", "operations", None, date(2026, 11, 16), 1.0),
            WorkloadItem("WL-03", "RES-07", "ticket", "PRJ-B", date(2026, 12, 1), 0.5),
        ),
    )
