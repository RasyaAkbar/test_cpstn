"""Import puti_datasets.xlsx ke PostgreSQL.

Alur:
1. Baca semua sheet workbook (`read_workbook`).
2. Validasi seluruh baris terhadap model di models.py (`validate`): kolom lengkap, tipe data,
   wajib isi, panjang teks, nilai yang diizinkan, urutan tanggal, rentang angka, kunci unik,
   foreign key, dan siklus dependency. Semua masalah dikumpulkan sekaligus, lengkap dengan
   nomor baris Excel.
3. Jika tidak ada masalah, ganti isi 11 tabel dataset dalam satu transaksi dan catat riwayat
   di dataset_imports (`load_dataset`). Jika ada masalah, database tidak disentuh.

Dari folder backend/:

    python -m app.modules.data.importer ../puti_datasets.xlsx --source synthetic --dry-run
    python -m app.modules.data.importer ../puti_datasets.xlsx --source synthetic
"""

import argparse
import hashlib
import math
import sys
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

from openpyxl import load_workbook
from openpyxl.utils.datetime import from_excel
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Date,
    Integer,
    Numeric,
    String,
    Table,
    UniqueConstraint,
    delete,
    insert,
)
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.modules.data.models import (
    DATA_SOURCES,
    DATASET_TABLES,
    DatasetImport,
    SemicolonList,
)

TRUE_TEXT = {"1", "true", "ya", "yes"}
FALSE_TEXT = {"0", "false", "tidak", "no"}
MAX_CYCLES_REPORTED = 5

# ─── Hasil validasi ───


@dataclass(frozen=True)
class Issue:
    sheet: str
    row: int | None  # nomor baris Excel (header = baris 1)
    column: str | None
    message: str

    def __str__(self) -> str:
        where = self.sheet
        if self.row is not None:
            where += f" baris {self.row}"
        if self.column:
            where += f" kolom {self.column}"
        return f"{where}: {self.message}"


@dataclass
class Dataset:
    """Baris yang sudah dikonversi ke tipe Python, per nama tabel database."""

    rows: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    row_numbers: dict[str, list[int]] = field(default_factory=dict)
    sheet_names: dict[str, str] = field(default_factory=dict)
    issues: list[Issue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.issues

    def counts(self) -> dict[str, int]:
        return {table: len(rows) for table, rows in self.rows.items()}

    def add(self, table: str, row_index: int | None, column: str | None, message: str) -> None:
        row = None if row_index is None else self.row_numbers[table][row_index]
        sheet = self.sheet_names.get(table, f"{table}_csv")
        self.issues.append(Issue(sheet, row, column, message))


# ─── Membaca workbook ───

RawSheet = tuple[list[str], list[tuple[int, dict[str, Any]]]]


def read_workbook(path: Path) -> dict[str, RawSheet]:
    """Nama sheet → (header, [(nomor baris Excel, {kolom: nilai mentah})])."""
    workbook = load_workbook(path, read_only=True, data_only=True)
    try:
        sheets: dict[str, RawSheet] = {}
        for sheet in workbook.worksheets:
            rows = sheet.iter_rows(values_only=True)
            header = [_header_cell(value) for value in next(rows, ())]
            while header and not header[-1]:
                header.pop()
            data = [
                (number, dict(zip(header, values)))
                for number, values in enumerate(rows, start=2)
                if not _is_blank_row(values)
            ]
            sheets[sheet.title] = (header, data)
        return sheets
    finally:
        workbook.close()


def _header_cell(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _is_blank_row(values: Sequence[Any]) -> bool:
    return all(value is None or (isinstance(value, str) and not value.strip()) for value in values)


def _find_sheet(raw: dict[str, RawSheet], table: str) -> str | None:
    for name in (f"{table}_csv", table, f"{table}.csv"):
        if name in raw:
            return name
    return None


# ─── Konversi nilai sel ───


def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int | float) and value in (0, 1):
        return bool(value)
    if isinstance(value, str) and value.lower() in TRUE_TEXT | FALSE_TEXT:
        return value.lower() in TRUE_TEXT
    raise ValueError(f"harus 0/1 atau TRUE/FALSE, bukan {value!r}")


def _to_date(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, int | float) and not isinstance(value, bool):
        return from_excel(value).date()  # nomor seri tanggal Excel
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError:
            pass
    raise ValueError(f"tanggal tidak valid: {value!r} (gunakan sel tanggal atau YYYY-MM-DD)")


def _to_int(value: Any) -> int:
    if isinstance(value, bool):
        raise ValueError(f"harus bilangan bulat, bukan {value!r}")
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        try:
            number = float(value)
        except ValueError:
            number = math.nan
        if number.is_integer():
            return int(number)
    raise ValueError(f"harus bilangan bulat, bukan {value!r}")


def _to_number(value: Any, scale: int | None) -> float:
    number = math.nan
    if isinstance(value, int | float) and not isinstance(value, bool):
        number = float(value)
    elif isinstance(value, str):
        try:
            number = float(value)  # koma ditolak: "1,000" bisa berarti 1 atau 1000
        except ValueError:
            pass
    if not math.isfinite(number):
        raise ValueError(f"harus angka, bukan {value!r}")
    if scale is not None:
        if abs(round(number, scale) - number) > 1e-9:
            raise ValueError(f"maksimal {scale} angka desimal, bukan {value!r}")
        number = round(number, scale)
    return number


def _to_text(value: Any, length: int | None) -> str:
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    text = str(value).strip()
    if length is not None and len(text) > length:
        raise ValueError(f"maksimal {length} karakter, panjangnya {len(text)}")
    return text


def _to_list(value: Any) -> list[str]:
    return [part.strip() for part in _to_text(value, None).split(";") if part.strip()]


def convert_cell(value: Any, column: Column) -> Any:
    """Ubah nilai sel Excel ke tipe Python kolom. ValueError berisi pesan untuk pengguna."""
    if isinstance(value, str) and not value.strip():
        value = None
    if value is None:
        if not column.nullable:
            raise ValueError("wajib diisi")
        return [] if isinstance(column.type, SemicolonList) else None

    kind = column.type
    if isinstance(kind, SemicolonList):
        return _to_list(value)
    if isinstance(kind, Boolean):
        return _to_bool(value)
    if isinstance(kind, Date):
        return _to_date(value)
    if isinstance(kind, Integer):
        return _to_int(value)
    if isinstance(kind, Numeric):
        return _to_number(value, kind.scale)
    if isinstance(kind, String):
        return _to_text(value, kind.length)
    raise TypeError(f"Tipe kolom {column} belum didukung importer")


# ─── Validasi ───


def validate(raw: dict[str, RawSheet]) -> Dataset:
    dataset = Dataset()
    unusable: set[str] = set()  # tabel tanpa sheet/kolom lengkap; FK ke sana tidak dicek

    for table in DATASET_TABLES:
        name = table.name
        sheet = _find_sheet(raw, name)
        dataset.rows[name], dataset.row_numbers[name] = [], []
        if sheet is None:
            dataset.add(name, None, None, f"sheet tidak ditemukan (nama sheet: {name}_csv)")
            unusable.add(name)
            continue
        dataset.sheet_names[name] = sheet

        header, data = raw[sheet]
        expected = [column.name for column in table.columns]
        missing = [column for column in expected if column not in header]
        unknown = [column for column in header if column not in expected]
        if missing:
            dataset.add(name, None, None, f"kolom hilang: {', '.join(missing)}")
            unusable.add(name)
        if unknown:
            dataset.add(name, None, None, f"kolom tidak dikenal: {', '.join(map(repr, unknown))}")
        if missing:
            continue

        dataset.row_numbers[name] = [number for number, _ in data]
        for index, (_, cells) in enumerate(data):
            row = {}
            for column in table.columns:
                try:
                    row[column.name] = convert_cell(cells.get(column.name), column)
                except ValueError as exc:
                    row[column.name] = None
                    dataset.add(name, index, column.name, str(exc))
            dataset.rows[name].append(row)

        _check_rules(dataset, table)
        _check_unique(dataset, table)

    _check_foreign_keys(dataset, unusable)
    _check_dependency_cycles(dataset, unusable)
    return dataset


def _check_rules(dataset: Dataset, table: Table) -> None:
    """Terapkan CHECK constraint model ke setiap baris, lewat `info` milik constraint."""
    rules = [c.info for c in table.constraints if isinstance(c, CheckConstraint)]
    for index, row in enumerate(dataset.rows[table.name]):
        for rule in rules:
            problem = rule_violation(rule, row)
            if problem:
                dataset.add(table.name, index, *problem)


def rule_violation(rule: dict, row: dict[str, Any]) -> tuple[str, str] | None:
    """(kolom, pesan) jika baris melanggar aturan; None jika lolos atau nilainya kosong."""
    if "one_of" in rule:
        column, allowed = rule["one_of"]
        value = row[column]
        if value is not None and value not in allowed:
            return column, f"nilai {value!r} tidak dikenal; pilihan: {', '.join(allowed)}"
    elif "ordered" in rule:
        first, second = rule["ordered"]
        if row[first] is not None and row[second] is not None and row[second] < row[first]:
            return second, f"{row[second]} lebih kecil dari {first} ({row[first]})"
    elif "in_range" in rule:
        column, minimum, maximum, exclusive = rule["in_range"]
        value = row[column]
        if value is None:
            return None
        if minimum is not None and (value <= minimum if exclusive else value < minimum):
            return column, f"{value} harus {'>' if exclusive else '>='} {minimum}"
        if maximum is not None and value > maximum:
            return column, f"{value} harus <= {maximum}"
    elif "distinct" in rule:
        first, second = rule["distinct"]
        if row[first] is not None and row[first] == row[second]:
            return second, f"tidak boleh sama dengan {first} ({row[first]})"
    else:
        raise KeyError(f"Aturan CHECK tanpa info yang dikenal importer: {rule}")
    return None


def _check_unique(dataset: Dataset, table: Table) -> None:
    keys = [tuple(column.name for column in table.primary_key.columns)]
    keys += [
        tuple(column.name for column in constraint.columns)
        for constraint in table.constraints
        if isinstance(constraint, UniqueConstraint)
    ]
    for columns in keys:
        first_seen: dict[tuple, int] = {}
        for index, row in enumerate(dataset.rows[table.name]):
            key = tuple(row[column] for column in columns)
            if any(part is None for part in key):
                continue
            if key in first_seen:
                earlier = dataset.row_numbers[table.name][first_seen[key]]
                label = ", ".join(map(str, key))
                dataset.add(
                    table.name,
                    index,
                    ", ".join(columns),
                    f"duplikat {label} (sudah ada di baris {earlier})",
                )
            else:
                first_seen[key] = index


def _check_foreign_keys(dataset: Dataset, unusable: set[str]) -> None:
    def keys_of(reference: str) -> set[Any]:
        table, column = reference.split(".")
        return {row[column] for row in dataset.rows[table]}

    for table in DATASET_TABLES:
        if table.name in unusable:
            continue
        references = [
            (fk.parent.name, f"{fk.column.table.name}.{fk.column.name}", False)
            for fk in table.foreign_keys
        ] + [
            (column.name, column.info["references_each"], True)
            for column in table.columns
            if "references_each" in column.info
        ]
        for column, reference, is_list in references:
            if reference.split(".")[0] in unusable:
                continue
            valid = keys_of(reference)
            for index, row in enumerate(dataset.rows[table.name]):
                values = row[column] if is_list else [row[column]]
                for value in values or ():
                    if value is not None and value not in valid:
                        dataset.add(
                            table.name, index, column, f"{value!r} tidak ada di {reference}"
                        )


def find_cycles(edges: Sequence[tuple[str, str]], limit: int) -> list[list[str]]:
    """Cari sampai `limit` siklus pada graf berarah (DFS iteratif)."""
    graph: dict[str, list[str]] = defaultdict(list)
    for source, target in edges:
        graph[source].append(target)
    state: dict[str, int] = {}  # 1 = sedang di jalur DFS, 2 = selesai
    cycles: list[list[str]] = []
    for root in list(graph):
        if root in state:
            continue
        state[root] = 1
        path, stack = [root], [iter(graph[root])]
        while stack:
            child = next(stack[-1], None)
            if child is None:
                state[path.pop()] = 2
                stack.pop()
            elif state.get(child) == 1:
                cycles.append(path[path.index(child) :] + [child])
                if len(cycles) >= limit:
                    return cycles
            elif child not in state:
                state[child] = 1
                path.append(child)
                stack.append(iter(graph[child]))
    return cycles


def _check_dependency_cycles(dataset: Dataset, unusable: set[str]) -> None:
    """Siklus membuat penjadwalan simulasi tidak pernah selesai (desain IV.2.3 langkah 4)."""
    if "task_dependencies" in unusable:
        return
    edges = [
        (row["task_id"], row["depends_on_task_id"])
        for row in dataset.rows["task_dependencies"]
        if row["task_id"] and row["depends_on_task_id"]
    ]
    for cycle in find_cycles(edges, MAX_CYCLES_REPORTED):
        dataset.add("task_dependencies", None, None, f"siklus dependency: {' -> '.join(cycle)}")


# ─── Menyimpan ke database ───


def load_dataset(
    session: Session, dataset: Dataset, *, source_file: str, file_sha256: str, data_source: str
) -> DatasetImport:
    """Ganti seluruh isi tabel dataset dalam satu transaksi."""
    if not dataset.ok:
        raise ValueError("Dataset masih memiliki masalah validasi; tidak ada yang disimpan")
    if data_source not in DATA_SOURCES:
        raise ValueError(f"data_source harus salah satu dari {DATA_SOURCES}")
    try:
        for table in reversed(DATASET_TABLES):
            session.execute(delete(table))
        for table in DATASET_TABLES:
            if dataset.rows[table.name]:
                session.execute(insert(table), dataset.rows[table.name])
        record = DatasetImport(
            source_file=source_file,
            file_sha256=file_sha256,
            data_source=data_source,
            row_counts=dataset.counts(),
        )
        session.add(record)
        session.commit()
    except Exception:
        session.rollback()
        raise
    return record


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ─── CLI ───


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m app.modules.data.importer",
        description="Validasi dan muat puti_datasets.xlsx ke tabel dataset PostgreSQL.",
    )
    parser.add_argument("path", type=Path, help="lokasi file .xlsx")
    parser.add_argument(
        "--source",
        required=True,
        choices=DATA_SOURCES,
        help="synthetic = data sintetis, puti = data asli PuTI (tampil di setiap layar)",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="validasi saja tanpa menulis ke database"
    )
    parser.add_argument(
        "--max-issues", type=int, default=50, help="jumlah masalah yang ditampilkan (bawaan 50)"
    )
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")

    if not args.path.is_file():
        print(f"File tidak ditemukan: {args.path}")
        return 2

    dataset = validate(read_workbook(args.path))
    for table, count in dataset.counts().items():
        print(f"  {table:<20} {count:>6} baris")

    if not dataset.ok:
        print(f"\n{len(dataset.issues)} masalah ditemukan; database tidak diubah.")
        for issue in dataset.issues[: args.max_issues]:
            print(f"  - {issue}")
        if len(dataset.issues) > args.max_issues:
            print(f"  ... dan {len(dataset.issues) - args.max_issues} masalah lain")
        return 1

    if args.dry_run:
        print("\nValid. Mode --dry-run: database tidak diubah.")
        return 0

    from app.db.session import SessionLocal  # impor di sini agar --dry-run tidak butuh database

    try:
        with SessionLocal() as session:
            record = load_dataset(
                session,
                dataset,
                source_file=args.path.name,
                file_sha256=file_sha256(args.path),
                data_source=args.source,
            )
    except SQLAlchemyError as exc:
        detail = getattr(exc, "orig", None) or exc
        print(f"\nGagal menulis ke database: {exc.__class__.__name__}: {detail}")
        print("Pastikan PostgreSQL aktif dan migrasi sudah dijalankan: alembic upgrade head")
        return 1

    print(
        f"\nSelesai: import #{record.import_id} ({record.data_source}) dari {record.source_file}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
