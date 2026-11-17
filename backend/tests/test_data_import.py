"""Tes import dataset (modul Data): validasi workbook, penyimpanan, dan endpoint status.

Workbook uji dibuat di folder sementara dengan struktur yang sama seperti puti_datasets.xlsx
(sheet `<tabel>_csv`), sehingga tes tidak bergantung pada file data. Database memakai SQLite
in-memory dengan foreign key aktif (fixture `db_session` di conftest.py); migrasi
PostgreSQL diuji terpisah lewat alembic.
"""

from datetime import date
from pathlib import Path
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook
from sqlalchemy import CheckConstraint, func, select, text
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.main import app
from app.modules.data.importer import (
    find_cycles,
    load_dataset,
    main,
    read_workbook,
    validate,
)
from app.modules.data.models import (
    DATASET_TABLES,
    DatasetImport,
    Project,
    Resource,
    Task,
)

PUTI_WORKBOOK = Path(__file__).resolve().parents[2] / "puti_datasets.xlsx"
COLUMNS = {table.name: [column.name for column in table.columns] for table in DATASET_TABLES}


def valid_rows() -> dict[str, list[dict]]:
    """Dataset kecil yang lolos semua aturan: 1 proyek, 2 anggota, 2 task berurutan."""
    return {
        "roles": [
            dict(
                role_id="ROLE-FE",
                role_name="Frontend Developer",
                capacity_reference=3.0,
                description="Pengembangan antarmuka web",
            ),
            dict(
                role_id="ROLE-QA",
                role_name="Quality Assurance",
                capacity_reference=2.5,
                description=None,
            ),
        ],
        "complexity_levels": [
            dict(
                complexity_id="CX-M",
                complexity_name="Medium",
                min_days=3.0,
                max_days=5.0,
                load_weight=0.9,
            )
        ],
        "projects": [
            dict(
                project_id="PRJ-001",
                project_name="LMS Akademik Terpadu",
                process_owner="Direktorat Akademik",
                priority_rank=1.0,
                start_date=date(2026, 1, 5),
                target_launch_date=date(2026, 6, 30),
                actual_launch_date=None,
                status="development",
                dor_fulfilled=True,
            )
        ],
        "resources": [
            dict(
                resource_id="RES-001",
                resource_name="Andi",
                primary_role_id="ROLE-FE",
                secondary_role_ids=None,
                cross_role_capable=False,
                join_date=date(2022, 4, 19),
                seniority="junior",
            ),
            dict(
                resource_id="RES-002",
                resource_name="Budi",
                primary_role_id="ROLE-QA",
                secondary_role_ids="ROLE-FE",
                cross_role_capable=True,
                join_date=date(2022, 7, 3),
                seniority="mid",
            ),
        ],
        "tasks": [
            dict(
                task_id="TSK-0001",
                project_id="PRJ-001",
                feature_name="Login",
                task_name="Login - Fe Dev",
                required_role_id="ROLE-FE",
                complexity_id="CX-M",
                priority_rank=1.0,
                estimated_days=4.5,
                phase="fe_dev",
                planned_start=date(2026, 2, 2),
                planned_finish=date(2026, 2, 6),
                actual_start=date(2026, 2, 2),
                actual_finish=date(2026, 2, 6),
                status="done",
                qa_reject_count=0.0,
                dod_fulfilled=True,
            ),
            dict(
                task_id="TSK-0002",
                project_id="PRJ-001",
                feature_name="Login",
                task_name="Login - Testing",
                required_role_id="ROLE-QA",
                complexity_id="CX-M",
                priority_rank=1.0,
                estimated_days=3.0,
                phase="testing",
                planned_start=date(2026, 2, 9),
                planned_finish=date(2026, 2, 11),
                actual_start=None,
                actual_finish=None,
                status="not_started",
                qa_reject_count=0.0,
                dod_fulfilled=False,
            ),
        ],
        "task_dependencies": [
            dict(
                dependency_id="DEP-0001",
                task_id="TSK-0002",
                depends_on_task_id="TSK-0001",
                dependency_type="hard",
                propagation_factor=1.0,
            )
        ],
        "assignments": [
            dict(
                assignment_id="ASG-00001",
                task_id="TSK-0001",
                resource_id="RES-001",
                role_in_task="ROLE-FE",
                assigned_date=date(2026, 2, 2),
                released_date=date(2026, 2, 6),
                is_takeover=False,
            ),
            dict(
                assignment_id="ASG-00002",
                task_id="TSK-0002",
                resource_id="RES-002",
                role_in_task="ROLE-QA",
                assigned_date=date(2026, 2, 9),
                released_date=None,
                is_takeover=False,
            ),
        ],
        "workload_items": [
            dict(
                item_id="WLI-0001",
                resource_id="RES-001",
                item_type="ticket",
                related_project_id="PRJ-001",
                received_date=date(2026, 3, 2),
                started_date=date(2026, 3, 3),
                resolved_date=None,
                severity="medium",
                is_hotfix=False,
            ),
            dict(
                item_id="WLI-0002",
                resource_id="RES-002",
                item_type="operational",
                related_project_id=None,
                received_date=date(2026, 3, 2),
                started_date=date(2026, 3, 2),
                resolved_date=date(2026, 3, 4),
                severity="low",
                is_hotfix=False,
            ),
        ],
        "availability": [
            dict(
                availability_id="AVL-0001",
                resource_id="RES-001",
                date_start=date(2026, 2, 16),
                date_end=date(2026, 2, 17),
                absence_type="planned_leave",
                is_known_at_planning=True,
            )
        ],
        "change_events": [
            dict(
                event_id="EVT-0001",
                project_id="PRJ-001",
                event_type="change_request",
                event_date=date(2026, 2, 3),
                requested_by="Kaur",
                decision="accept_now",
                resolution_mode="scope_addition",
                affected_task_id="TSK-0001",
                extension_days=1.5,
            )
        ],
        "holidays": [dict(holiday_date=date(2026, 1, 1), holiday_name="Tahun Baru Masehi")],
    }


def write_workbook(
    folder: Path,
    rows: dict[str, list[dict]],
    *,
    name: str = "dataset.xlsx",
    drop_columns: dict[str, list[str]] | None = None,
    extra_columns: dict[str, list[str]] | None = None,
) -> Path:
    workbook = Workbook()
    workbook.remove(workbook.active)
    for table, records in rows.items():
        header = [c for c in COLUMNS[table] if c not in (drop_columns or {}).get(table, [])]
        header += (extra_columns or {}).get(table, [])
        sheet = workbook.create_sheet(f"{table}_csv")
        sheet.append(header)
        for record in records:
            sheet.append([record.get(column) for column in header])
    path = folder / name
    workbook.save(path)
    return path


def validated(folder: Path, rows: dict[str, list[dict]], **kwargs):
    return validate(read_workbook(write_workbook(folder, rows, **kwargs)))


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def load(session: Session, dataset) -> DatasetImport:
    return load_dataset(
        session,
        dataset,
        source_file="dataset.xlsx",
        file_sha256="0" * 64,
        data_source="synthetic",
    )


# ─── Validasi dan penyimpanan ───


def test_valid_workbook_is_stored_with_excel_types(tmp_path, db_session):
    dataset = validated(tmp_path, valid_rows())
    assert dataset.issues == []

    record = load(db_session, dataset)

    assert record.row_counts["tasks"] == 2
    assert db_session.get(Resource, "RES-002").secondary_role_ids == ["ROLE-FE"]
    assert db_session.get(Resource, "RES-001").secondary_role_ids == []
    task = db_session.get(Task, "TSK-0001")
    assert (task.estimated_days, task.priority_rank, task.dod_fulfilled) == (4.5, 1, True)
    assert task.planned_start == date(2026, 2, 2)
    stored = db_session.execute(
        text("SELECT secondary_role_ids FROM resources ORDER BY resource_id")
    ).scalars()
    assert list(stored) == [None, "ROLE-FE"]  # sama persis dengan sel Excel


def test_reimport_replaces_rows_and_keeps_import_history(tmp_path, db_session):
    dataset = validated(tmp_path, valid_rows())
    load(db_session, dataset)
    load(db_session, dataset)

    assert db_session.scalar(select(func.count()).select_from(Task)) == 2
    assert db_session.scalar(select(func.count()).select_from(DatasetImport)) == 2


@pytest.mark.parametrize(
    ("table", "index", "column", "value", "message"),
    [
        ("tasks", 0, "status", "archived", "nilai 'archived' tidak dikenal"),
        ("tasks", 0, "planned_finish", date(2026, 1, 1), "lebih kecil dari planned_start"),
        ("tasks", 0, "project_id", "PRJ-999", "'PRJ-999' tidak ada di projects.project_id"),
        ("tasks", 0, "estimated_days", 1.234, "maksimal 2 angka desimal"),
        ("tasks", 0, "priority_rank", 1.5, "harus bilangan bulat"),
        ("tasks", 0, "task_name", None, "wajib diisi"),
        ("tasks", 1, "task_id", "TSK-0001", "duplikat TSK-0001 (sudah ada di baris 2)"),
        ("projects", 0, "dor_fulfilled", "mungkin", "harus 0/1 atau TRUE/FALSE"),
        ("resources", 1, "secondary_role_ids", "ROLE-FE;ROLE-XX", "'ROLE-XX' tidak ada"),
        ("task_dependencies", 0, "propagation_factor", 1.5, "harus <= 1"),
        ("task_dependencies", 0, "depends_on_task_id", "TSK-0002", "tidak boleh sama"),
    ],
)
def test_issue_points_to_sheet_row_and_column(tmp_path, table, index, column, value, message):
    rows = valid_rows()
    rows[table][index][column] = value

    issues = validated(tmp_path, rows).issues

    matching = [issue for issue in issues if message in issue.message]
    assert matching, [str(issue) for issue in issues]
    assert (matching[0].sheet, matching[0].row, matching[0].column) == (
        f"{table}_csv",
        index + 2,  # baris 1 = header
        column,
    )


def test_missing_sheet_and_column_mismatch_are_reported_without_noise(tmp_path):
    rows = valid_rows()
    del rows["holidays"]

    issues = validated(
        tmp_path,
        rows,
        drop_columns={"tasks": ["phase"]},
        extra_columns={"roles": ["catatan"]},
    ).issues

    assert sorted(str(issue) for issue in issues) == [
        "holidays_csv: sheet tidak ditemukan (nama sheet: holidays_csv)",
        "roles_csv: kolom tidak dikenal: 'catatan'",
        "tasks_csv: kolom hilang: phase",
    ]


def test_dependency_cycle_is_reported(tmp_path):
    rows = valid_rows()
    rows["task_dependencies"].append(
        dict(
            dependency_id="DEP-0002",
            task_id="TSK-0001",
            depends_on_task_id="TSK-0002",
            dependency_type="soft",
            propagation_factor=0.3,
        )
    )

    issues = validated(tmp_path, rows).issues

    assert [str(issue) for issue in issues] == [
        "task_dependencies_csv: siklus dependency: TSK-0002 -> TSK-0001 -> TSK-0002"
    ]


def test_find_cycles_ignores_diamond_shaped_dependencies():
    edges = [("D", "B"), ("D", "C"), ("B", "A"), ("C", "A")]
    assert find_cycles(edges, limit=5) == []


def test_invalid_dataset_is_never_written(tmp_path, db_session):
    rows = valid_rows()
    rows["tasks"][0]["status"] = "archived"
    with pytest.raises(ValueError, match="masalah validasi"):
        load(db_session, validated(tmp_path, rows))
    assert db_session.scalar(select(func.count()).select_from(Task)) == 0


def test_every_check_constraint_is_also_checked_by_importer():
    known = {"one_of", "ordered", "in_range", "distinct"}
    for table in DATASET_TABLES:
        for constraint in table.constraints:
            if isinstance(constraint, CheckConstraint):
                assert known & set(constraint.info), f"{table.name}.{constraint.name}"


def test_database_rejects_rows_that_bypass_the_importer(db_session):
    db_session.add(
        Project(
            project_id="PRJ-X",
            project_name="Uji",
            process_owner="Uji",
            priority_rank=1,
            start_date=date(2026, 1, 5),
            target_launch_date=date(2026, 6, 30),
            status="archived",
            dor_fulfilled=True,
        )
    )
    with pytest.raises(IntegrityError):
        db_session.commit()


@pytest.mark.skipif(not PUTI_WORKBOOK.is_file(), reason="puti_datasets.xlsx tidak ada di root repo")
def test_puti_workbook_matches_database_schema():
    raw = read_workbook(PUTI_WORKBOOK)
    for table in DATASET_TABLES:
        header, _ = raw[f"{table.name}_csv"]
        assert header == COLUMNS[table.name], table.name  # kolom dan urutannya sama persis

    dataset = validate(raw)

    assert [str(issue) for issue in dataset.issues] == []
    assert all(dataset.counts().values())


# ─── CLI ───


def test_cli_dry_run_reports_issues_and_exit_code(tmp_path, capsys):
    good = write_workbook(tmp_path, valid_rows(), name="baik.xlsx")
    assert main([str(good), "--source", "synthetic", "--dry-run"]) == 0

    rows = valid_rows()
    rows["tasks"][0]["status"] = "archived"
    bad = write_workbook(tmp_path, rows, name="salah.xlsx")
    assert main([str(bad), "--source", "synthetic", "--dry-run"]) == 1
    assert "tasks_csv baris 2 kolom status" in capsys.readouterr().out


# ─── Endpoint status ───


def test_status_endpoint_before_and_after_import(tmp_path, db_session, client):
    app.dependency_overrides[get_db] = lambda: db_session

    empty = client.get("/api/v1/data/status").json()
    load(db_session, validated(tmp_path, valid_rows()))
    loaded = client.get("/api/v1/data/status").json()

    assert empty["latest_import"] is None
    assert {row["table"] for row in empty["tables"]} == set(COLUMNS)
    assert all(row["rows"] == 0 for row in empty["tables"])
    assert loaded["latest_import"]["data_source"] == "synthetic"
    assert {row["table"]: row["rows"] for row in loaded["tables"]}["tasks"] == 2


def test_status_endpoint_returns_503_when_database_is_down(client):
    session = Mock()
    session.scalars.side_effect = OperationalError("SELECT", {}, Exception("rahasia"))
    app.dependency_overrides[get_db] = lambda: session

    response = client.get("/api/v1/data/status")

    assert response.status_code == 503
    assert response.json() == {"detail": "Database atau tabel dataset belum siap"}
