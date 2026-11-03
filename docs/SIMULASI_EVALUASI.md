# Iterasi 1–2: Simulasi What-if dan KPI

Dokumen ini memetakan kode Iterasi 1 (scenario setup + what-if simulation) dan Iterasi 2 (KPI + perbandingan dengan baseline) ke anggota tim dan ke desain di Bab IV proposal. Setiap file juga diberi tanda `PEMILIK:` di baris atasnya, dan bagian di dalam file dipisah dengan komentar `# ─── ... ───` (Python) atau `// ─── ... ───` (TypeScript).

| Peran | Cakupan | Folder |
| --- | --- | --- |
| **Orang 1 — Frontend** | Semua layar Simulasi dan Evaluasi | `frontend/src/modules/simulasi/`, `frontend/src/modules/evaluasi/`, `frontend/src/shared/format.ts`, tambahan di `shared/api/client.ts` dan `styles/components.css` |
| **Orang 2 — Simulasi** | Model baseline, scenario setup, aturan skenario, mesin simulasi | `backend/app/modules/simulasi/`, `backend/tests/test_simulasi.py`, `backend/tests/conftest.py` |
| **Orang 3 — KPI** | Definisi KPI, perhitungan KPI, perbandingan baseline vs skenario, skenario terbaik | `backend/app/modules/evaluasi/`, `backend/tests/test_evaluasi.py` |

## Alur data

```text
baseline.py ──► rules.apply_scenario() ──► engine.run_simulation() / run_replications()
 (Orang 2)        salinan baseline            SimulationResult (kontrak Orang 2 → Orang 3)
                                                     │
                                  ┌──────────────────┴──────────────────┐
                    service.run_response() (Orang 2)       kpi.compute_kpis() (Orang 3)
                    POST /simulasi/scenarios/{id}/run      comparison.compare() → POST /evaluasi/compare
                                  │                                     │
                    SimulationResultView.tsx (Orang 1)     KpiComparison.tsx (Orang 1)
```

Kontrak antar orang:

- **Orang 2 → Orang 3**: `SimulationResult`, `TaskOutcome`, `ResourceOutcome` di `engine.py` (bagian "Hasil simulasi"), serta `apply_scenario()` dan `Snapshot`. Jangan mengganti nama field tanpa memberi tahu Orang 3.
- **Orang 2 → Orang 1**: `simulasi/schemas.py` ↔ `frontend/src/modules/simulasi/api.ts`.
- **Orang 3 → Orang 1**: `evaluasi/schemas.py` ↔ `frontend/src/modules/evaluasi/api.ts`. Label, satuan, dan arah KPI dikirim backend lewat `GET /evaluasi/kpi-definitions`, jadi frontend tidak menulis ulang daftar KPI.

## Orang 2 — Simulasi (`backend/app/modules/simulasi/`)

| File | Bagian / fungsi | Fungsi dalam desain |
| --- | --- | --- |
| `domain.py` | `Project`, `Role`, `Resource`, `Task`, `Dependency`, `Assignment`, `Availability`, `Holiday`, `WorkloadItem`, `Snapshot` | Model baseline sesuai kolom Tabel 4.3 (langkah 1 IV.2.3). Field `[sim]` bukan kolom CSV PuTI. |
| `synthetic_data.py` | `build_synthetic_snapshot()` | Data sintetis: 3 proyek, 8 anggota (pseudonim), 27 task. |
| `baseline.py` | `get_baseline_snapshot()` | Satu-satunya titik masuk baseline; ganti di sini saat data PuTI tersedia. |
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
| `kpi.py` | `KPI_DEFINITIONS` | **Definisi KPI**: kunci, label, satuan, arah lebih baik, penjelasan (dari "Candidate KPIs" I.4.2). |
| `kpi.py` | `project_kpis()` | Tanggal selesai proyek, keterlambatan, target launch tercapai atau tidak. |
| `kpi.py` | `member_loads()` | Beban anggota terhadap kapasitas sampai target proyeknya. |
| `kpi.py` | `tasks_delayed_by_dependency()`, `tasks_dropped_or_deferred()` | KPI dependency dan task di-drop/lewat target. |
| `kpi.py` | `compute_kpis()` | Menghitung semua KPI satu run (FR-05, UC-05). |
| `comparison.py` | `percentile()`, `_distribution()` | Median dan rentang P10–P90 dari replikasi. |
| `comparison.py` | `kpi_status()`, `_evaluation()` | **Perbandingan dengan baseline**: delta skenario − baseline dan status lebih baik/buruk (FR-06). |
| `comparison.py` | `RANKING_ORDER`, `rank_scenarios()` | Skenario terbaik (UC-06). |
| `comparison.py` | `compare()` | Alur lengkap perbandingan. |
| `schemas.py` | `CompareRequest`, `CompareResponse`, `Evaluation`, `KpiValue` | Kontrak API ke frontend. |
| `router.py` | `GET /api/v1/evaluasi/kpi-definitions`, `POST /api/v1/evaluasi/compare` | UC-05, UC-06. |

KPI yang dihitung (semua "makin kecil makin baik"):

| Kunci | KPI | Dari Candidate KPIs (I.4.2) |
| --- | --- | --- |
| `projects_missing_target` | Proyek melewati target launch | whether the launch target still holds |
| `total_delay_days`, `max_delay_days` | Keterlambatan terhadap target | delay in days |
| `completion_span_days` | Durasi sampai semua proyek selesai | projected completion date |
| `overloaded_members`, `max_member_load_pct` | Beban anggota | load per member against capacity |
| `tasks_delayed_by_dependency` | Task tertunda karena dependency | tasks delayed through dependencies |
| `tasks_dropped_or_deferred` | Task di-drop atau lewat target | tasks dropped or deferred |
| `idle_capacity_days` | Kapasitas hilang karena menunggu | gap "capacity lost to dependencies" (Tabel 1.1) |

Skenario terbaik diurutkan secara leksikografis: proyek melewati target → total keterlambatan → anggota overload → beban tertinggi → durasi. "Terbaik" berarti paling kecil dampaknya; keputusan tetap di Kepala Seksi dan System Analyst.

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
| `modules/evaluasi/KpiComparison.tsx` | `KpiComparison`, `KpiCell`, `ProjectCell` | KPI and scenario comparison |
| `shared/format.ts` | `formatDate`, `formatSigned`, `addDays`, `daysBetween` | Dipakai kedua halaman |
| `shared/api/client.ts` | `apiPost`, `apiPut`, `apiDelete`, `ApiError` | Tambahan untuk POST/PUT/DELETE |
| `styles/components.css` | Bagian "Form, tabel, dan status" | Komponen form/tabel bersama |
| `modules/*/simulasi.css`, `evaluasi.css` | Tata letak per halaman | — |

## Asumsi yang perlu dikonfirmasi ke PuTI

Asumsi ini memengaruhi angka hasil dan harus dicek saat validasi (III.3.3):

1. `propagation_factor` = porsi predecessor yang harus selesai sebelum task boleh mulai (1.0 = finish-to-start penuh). `engine._schedule()`.
2. `capacity_reference` role = hari-orang kerja proyek per hari kerja (SA 0.6, lainnya 0.8 di data sintetis). Sisanya dianggap operasional rutin.
3. Kerja di role sekunder 75% seefektif role utama (`CROSS_ROLE_EFFICIENCY`).
4. Onboarding naik linear dari kapasitas awal ke 100% selama `onboarding_days`; mentor kehilangan `mentor_overhead` per hari selama onboarding.
5. Tiket dan hotfix dikerjakan sebelum task fitur; anggota lintas proyek mendahulukan proyek berprioritas tinggi.
6. Beban anggota = pekerjaan yang ditanggung / kapasitas sampai target proyek terakhir yang ia kerjakan; overload jika > 100%.

## Batasan Iterasi 1–2

- Baseline masih data sintetis (`data_source = "synthetic"`, ditampilkan di setiap layar). Hasil menunjukkan perilaku sistem, bukan prakiraan proyek PuTI.
- Skenario disimpan di memori proses dan hilang saat backend restart. Pindahkan ke PostgreSQL (model + migrasi Alembic) dengan method `ScenarioStore` yang sama.
- `load_weight` kompleksitas dan `task_priorities` di skenario perubahan prioritas sudah ada di kontrak API, tetapi belum dipakai di form/perhitungan.
- Decision support (rekomendasi + alasan) dan laporan adalah Iterasi 3.

## Menjalankan dan menguji

```powershell
# backend/
.\.venv\Scripts\python.exe -m pytest tests/test_simulasi.py   # Orang 2
.\.venv\Scripts\python.exe -m pytest tests/test_evaluasi.py   # Orang 3
# frontend/
npm run build                                                  # Orang 1
```

Tes memakai baseline kecil di `tests/conftest.py` yang hasilnya bisa dihitung manual (validasi "independently calculated examples", III.3.3). Contoh: task 3 hari mulai Senin selesai Rabu; libur hari Selasa membuatnya selesai Kamis.
