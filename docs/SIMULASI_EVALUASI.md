# Iterasi 1–2: Simulasi What-if dan KPI

Dokumen ini memetakan kode Iterasi 1 (scenario setup + what-if simulation) dan Iterasi 2 (KPI + perbandingan dengan baseline) ke anggota tim dan ke desain di Bab IV proposal. Setiap file juga diberi tanda `PEMILIK:` di baris atasnya, dan bagian di dalam file dipisah dengan komentar `# ─── ... ───` (Python) atau `// ─── ... ───` (TypeScript).

| Peran | Cakupan | Folder |
| --- | --- | --- |
| **Orang 1 — Frontend** | Semua layar Simulasi dan Evaluasi | `frontend/src/modules/simulasi/`, `frontend/src/modules/evaluasi/`, `frontend/src/shared/format.ts`, tambahan di `shared/api/client.ts` dan `styles/components.css` |
| **Orang 2 — Simulasi** | Model baseline, scenario setup, aturan skenario, mesin simulasi | `backend/app/modules/simulasi/`, `backend/tests/test_simulasi.py`, `backend/tests/conftest.py` |
| **Orang 3 — KPI** | Definisi KPI, perhitungan KPI, perbandingan baseline vs skenario, skenario terbaik | `backend/app/modules/evaluasi/`, `backend/tests/test_evaluasi.py` |

## Alur data

```text
puti_datasets.xlsx ──► data/importer.py ──► PostgreSQL (11 tabel dataset + dataset_imports)
                                                 │
                         db_baseline.snapshot_from_rows()  ← baseline.get_baseline_snapshot()
                                                 │            (cache per import)
baseline Snapshot ──► rules.apply_scenario() ──► engine.run_simulation() / run_replications()
 (Orang 2)              salinan baseline            SimulationResult (kontrak Orang 2 → Orang 3)
                                                     │
                                  ┌──────────────────┴──────────────────┐
                    service.run_response() (Orang 2)       kpi.compute_kpis() (Orang 3)
                    POST /simulasi/scenarios/{id}/run      comparison.compare() → POST /evaluasi/compare
                                  │                        historical.historical_kpis() → GET /evaluasi/historical
                    SimulationResultView.tsx (Orang 1)     KpiComparison.tsx, HistoricalPanel.tsx (Orang 1)
```

Baseline API selalu dibaca dari import terakhir di database. Jika belum ada import, endpoint simulasi/evaluasi menjawab 503 dengan perintah importer yang perlu dijalankan.

Kontrak antar orang:

- **Orang 2 → Orang 3**: `SimulationResult`, `TaskOutcome`, `ResourceOutcome` di `engine.py` (bagian "Hasil simulasi"), serta `apply_scenario()` dan `Snapshot`. Jangan mengganti nama field tanpa memberi tahu Orang 3.
- **Orang 2 → Orang 1**: `simulasi/schemas.py` ↔ `frontend/src/modules/simulasi/api.ts`.
- **Orang 3 → Orang 1**: `evaluasi/schemas.py` ↔ `frontend/src/modules/evaluasi/api.ts`. Label, satuan, dan arah KPI dikirim backend lewat `GET /evaluasi/kpi-definitions`, jadi frontend tidak menulis ulang daftar KPI.

## Orang 2 — Simulasi (`backend/app/modules/simulasi/`)

| File | Bagian / fungsi | Fungsi dalam desain |
| --- | --- | --- |
| `domain.py` | `Project`, `Role`, `Resource`, `Task`, `Dependency`, `Assignment`, `Availability`, `Holiday`, `WorkloadItem`, `TaskRecord`, `Snapshot`, `WORK_WEIGHTS` | Model baseline sesuai kolom Tabel 4.3 (langkah 1 IV.2.3). Field `[sim]` bukan kolom CSV PuTI. |
| `db_baseline.py` | `snapshot_from_rows()`, `bau_shares()`, `blocker_days()`, `REMAINING_SHARE` | Menyiapkan Snapshot dari tabel dataset: tanggal mulai, sisa effort, porsi BAU, role dari assignment. Asumsinya juga dikirim ke layar lewat `Snapshot.notes`. |
| `baseline.py` | `get_baseline_snapshot()` | Satu-satunya titik masuk baseline: import terakhir di database, di-cache per import. |
| `synthetic_data.py` | `build_synthetic_snapshot()` | Data sintetis kecil untuk tes: 3 proyek, 8 anggota (pseudonim), 27 task. |
| `schemas.py` | `ChangeRequestParams` … `CriticalBugParams`, `ScenarioInput`, `Scenario` | Parameter 8 situasi (Tabel 4.2/4.4), FR-01/FR-02. |
| `schemas.py` | `BaselineResponse`, `SimulationRunResponse`, `ProjectOutcome`, `TaskChange`, `ResourceLoad` | Respons API untuk form dan hasil simulasi (FR-04). |
| `store.py` | `ScenarioStore.create/update/delete/duplicate` | Simpan dan duplikat skenario (FR-02, UC-02). |
| `rules.py` | `_apply_change_request` … `_apply_critical_bug`, `apply_scenario()` | Langkah 2 IV.2.3: terapkan skenario ke salinan baseline. |
| `rules.py` | `pick_cover()` | Pilih pengganti dengan role sama dan beban terkecil (praktik PuTI, Tabel 1.1). |
| `engine.py` | `WorkCalendar`, `_onboarding_factor()`, `_capacity_profile()` | Langkah 3: kapasitas harian (hari kerja, libur, cuti, onboarding, mentor). |
| `engine.py` | `_prepare()`, `_schedule()`, `run_simulation()` | Langkah 4–5: jadwal hari demi hari, dependency, prioritas, hotfix dulu. |
| `engine.py` | `sample_effort()`, `run_replications()` | Replikasi Monte Carlo (distribusi segitiga min–max kompleksitas). |
| `service.py` | `simulate_pair()`, `run_response()`, `baseline_response()` | Menyusun hasil baseline vs skenario per proyek, task, dan beban mingguan. |
| `router.py` | Semua endpoint `/api/v1/simulasi/...` | UC-01 s.d. UC-04. |

Endpoint:

| Method | Path | Use case |
| --- | --- | --- |
| GET | `/api/v1/simulasi/baseline` | Pilihan form (proyek, anggota, task, role) |
| GET / POST | `/api/v1/simulasi/scenarios` | Daftar / buat skenario (UC-01) |
| GET / PUT / DELETE | `/api/v1/simulasi/scenarios/{id}` | Detail / ubah / hapus (UC-02) |
| POST | `/api/v1/simulasi/scenarios/{id}/duplicate` | Duplikat (UC-02) |
| POST | `/api/v1/simulasi/scenarios/{id}/run` | Jalankan simulasi vs baseline (UC-03, UC-04) |

## Orang 3 — KPI (`backend/app/modules/evaluasi/`)

| File | Bagian / fungsi | Fungsi dalam desain |
| --- | --- | --- |
| `kpi.py` | `KPI_DEFINITIONS` | **Definisi KPI**: kunci, nomor FR, label, satuan, arah lebih baik, rumus (dari "FR Dashboard Digital Twin - Formula KPI"). |
| `kpi.py` | `project_kpis()` | Schedule Variance per proyek dalam hari kerja (FR-04.1). |
| `kpi.py` | `weekly_rli()`, `sustained_overload()`, `workload_balance()` | RLI mingguan, overload, SOI, WBI (FR-04.3 s.d. FR-04.6). |
| `kpi.py` | `cascade_delay()` | Cascade Delay Impact per task (FR-04.7). |
| `kpi.py` | `compute_kpis()` | Menghitung semua KPI satu run (FR-05, UC-05). |
| `historical.py` | `historical_kpis()` | EAR dan Rework Rate dari data aktual (FR-04.8, FR-04.9). |
| `comparison.py` | `percentile()`, `_distribution()`, `on_time_probabilities()` | Median, P10–P90, dan On-Time Launch Probability dari replikasi (FR-04.2). |
| `comparison.py` | `kpi_status()`, `_evaluation()` | **Perbandingan dengan baseline**: delta skenario − baseline dan status lebih baik/buruk (FR-06). |
| `comparison.py` | `RANKING_ORDER`, `rank_scenarios()` | Skenario terbaik (UC-06); KPI "makin besar makin baik" dibalik saat diurutkan. |
| `comparison.py` | `compare()` | Alur lengkap perbandingan. |
| `schemas.py` | `CompareRequest`, `CompareResponse`, `Evaluation`, `KpiValue`, `HistoricalResponse` | Kontrak API ke frontend. |
| `router.py` | `GET /kpi-definitions`, `POST /compare`, `GET /historical` | UC-05, UC-06. |

KPI per skenario (dibandingkan dengan baseline):

| Kunci | FR | KPI | Lebih baik |
| --- | --- | --- | --- |
| `projects_late`, `sv_total_days`, `sv_max_days` | FR-04.1 | Schedule Variance: launch hasil simulasi − target (hari kerja) | kecil |
| `on_time_probability` | FR-04.2 | Rata-rata proyek dari porsi replikasi dengan SV ≤ 0 (butuh replikasi > 0) | besar |
| `rli_peak` | FR-04.3 | RLI = (1.0 × task aktif + 0.5 × operasional + 0.3 × tiket) / capacity_reference | kecil |
| `overload_resource_weeks` | FR-04.4 | Pasangan (anggota, minggu) dengan RLI > threshold (bawaan 1.0, bisa diubah per perbandingan) | kecil |
| `wbi` | FR-04.5 | 1 − CV(RLI antar anggota) per minggu, dirata-rata | besar |
| `soi_max`, `sustained_overload_resources` | FR-04.6 | Minggu overload berturut-turut (≥ 2) × rata-rata kelebihan; episode terberat | kecil |
| `cdi_max` | FR-04.7 | Keterlambatan task × Σ faktor propagasi ke task hilir (jalur terkuat) | kecil |
| `blocked_ratio`, `reallocated_ratio` | FR-04.10 | Kapasitas menganggur saat menunggu / total kapasitas; waktu tunggu yang terisi task independen / total waktu tunggu | kecil / besar |

KPI historis (sama untuk semua skenario, `GET /evaluasi/historical`): EAR (FR-04.8) = Σ durasi aktual (hari kerja) / Σ estimasi per kompleksitas dan role; Rework Rate (FR-04.9) = task dengan `qa_reject_count > 0` / task yang masuk QA, per role dan proyek.

Skenario terbaik diurutkan secara leksikografis: proyek terlambat → total SV → anggota overload berkelanjutan → minggu-anggota overload → WBI. "Terbaik" berarti paling kecil dampaknya; keputusan tetap di Kepala Seksi dan System Analyst.

## Orang 1 — Frontend (`frontend/src/`)

| File | Komponen / fungsi | Layar (Tabel 4.7) |
| --- | --- | --- |
| `modules/simulasi/api.ts` | Tipe + `getBaseline`, `createScenario`, `runScenario`, … | Kontrak ke backend Orang 2 |
| `modules/simulasi/situations.ts` | `SITUATIONS` (label, field, nilai awal per situasi) | Scenario setup |
| `modules/simulasi/ScenarioForm.tsx` | `ScenarioForm`, `FieldInput`, `ChangeRequestEditor` | Scenario setup (form parameter) |
| `modules/simulasi/SimulasiPage.tsx` | `SimulasiPage` (daftar skenario, simpan, duplikat, hapus, jalankan) | Scenario setup + Simulation result |
| `modules/simulasi/SimulationResultView.tsx` | `KpiSummary`, `ProjectTable`, `ScheduleTable` (Gantt), `LoadHeatmap` | Simulation result |
| `modules/evaluasi/api.ts` | Tipe + `getKpiDefinitions`, `compareScenarios` | Kontrak ke backend Orang 3 |
| `modules/evaluasi/EvaluasiPage.tsx` | `EvaluasiPage` (pilih skenario, jumlah replikasi) | KPI and scenario comparison |
| `modules/evaluasi/KpiComparison.tsx` | `KpiComparison`, `KpiCell`, `ProjectCell`, `CascadeTable` | KPI and scenario comparison (SV, RLI/SOI, CDI) |
| `modules/evaluasi/HistoricalPanel.tsx` | `HistoricalPanel`, `RatioTable` | EAR, Rework Rate, dan catatan penyiapan data |
| `shared/format.ts` | `formatDate`, `formatSigned`, `addDays`, `daysBetween` | Dipakai kedua halaman |
| `shared/api/client.ts` | `apiPost`, `apiPut`, `apiDelete`, `ApiError` | Tambahan untuk POST/PUT/DELETE |
| `styles/components.css` | Bagian "Form, tabel, dan status" | Komponen form/tabel bersama |
| `modules/*/simulasi.css`, `evaluasi.css` | Tata letak per halaman | — |

## Asumsi yang perlu dikonfirmasi ke PuTI

Asumsi ini memengaruhi angka hasil dan harus dicek saat validasi (III.3.3):

1. `propagation_factor` = porsi predecessor yang harus selesai sebelum task boleh mulai (hard 1.0 = finish-to-start penuh, soft 0.3). Faktor yang sama dipakai CDI. `engine._schedule()`.
2. Simulasi mulai hari kerja setelah kejadian terakhir di dataset (`as_of` = tanggal actual/assignment/workload/change event terbaru). `db_baseline.observed_until()`.
3. Proyek berstatus `released` dan task `dropped` tidak dijadwalkan; tetap dihitung di KPI historis.
4. Sisa effort tanpa time tracking: `not_started`/`on_hold` 100%, `in_progress`/`blocked` 50%, `in_qa` 20% dari `estimated_days` (`REMAINING_SHARE`). Task `blocked` tertahan rata-rata `extension_days` event blocker (dibulatkan ke atas).
5. Kapasitas harian anggota = 1 hari-orang dikurangi porsi BAU: beban historis tiket (0.3) dan operasional (0.5) selama terbuka, dibagi `capacity_reference` dan hari kerja pengamatan. Porsi yang sama menjadi komponen tiket/operasional pada RLI.
6. `capacity_reference` role (3.0) = jumlah beban setara task proyek yang bisa dipegang bersamaan (penyebut RLI), bukan hari-orang per hari. Di data sintetis tes, kapasitas harian role tetap 0.6–0.8.
7. Assignment dianggap benar: role yang tidak tercatat di master anggota menjadi role sekunder (efisiensi 75%, `CROSS_ROLE_EFFICIENCY`).
8. Task proyek "aktif" pada RLI = task yang sudah berjalan di baseline (sejak hari ke-0) atau yang mulai dikerjakan di simulasi, sampai selesai.
9. Onboarding naik linear dari kapasitas awal ke 100% selama `onboarding_days`; mentor kehilangan `mentor_overhead` per hari selama onboarding.
10. Tiket dan hotfix dikerjakan sebelum task fitur; anggota lintas proyek mendahulukan proyek berprioritas tinggi.
11. Semua availability (cuti, rotasi masuk/keluar) dianggap anggota tidak tersedia. Hari libur hanya yang ada di `holidays_csv`.

## Batasan

- Di dataset saat ini semua target launch proyek aktif sudah lewat sebelum `as_of`, sehingga On-Time Launch Probability selalu 0%. KPI ini baru informatif untuk target di masa depan.
- 100 replikasi × (baseline + 5 skenario) memakan puluhan detik untuk ~450 task terbuka. Jika perlu lebih cepat, replikasi bisa dijalankan paralel per proses.
- Skenario disimpan di memori proses dan hilang saat backend restart. Pindahkan ke PostgreSQL (model + migrasi Alembic) dengan method `ScenarioStore` yang sama.
- `load_weight` kompleksitas dan `task_priorities` di skenario perubahan prioritas sudah ada di kontrak API, tetapi belum dipakai di form/perhitungan.
- Decision support (rekomendasi + alasan) dan laporan adalah Iterasi 3.

## Menjalankan dan menguji

```powershell
# backend/ — muat dataset ke database sebelum membuka halaman Simulasi/Evaluasi
.\.venv\Scripts\python.exe -m app.modules.data.importer ..\puti_datasets.xlsx --source synthetic
.\.venv\Scripts\python.exe -m pytest tests/test_simulasi.py tests/test_db_baseline.py   # Orang 2
.\.venv\Scripts\python.exe -m pytest tests/test_evaluasi.py                             # Orang 3
# frontend/
npm run build                                                  # Orang 1
```

Tes memakai baseline kecil di `tests/conftest.py` yang hasilnya bisa dihitung manual (validasi "independently calculated examples", III.3.3). Contoh: task 3 hari mulai Senin selesai Rabu; libur hari Selasa membuatnya selesai Kamis.
