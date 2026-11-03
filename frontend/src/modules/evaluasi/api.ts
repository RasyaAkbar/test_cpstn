/* Klien API modul evaluasi (KPI).
   PEMILIK: Orang 1 — Frontend. Tipe di file ini mencerminkan
   backend/app/modules/evaluasi/schemas.py (Orang 3); ubah keduanya bersamaan. */

import { apiGet, apiPost } from '../../shared/api/client';

export type KpiDefinition = { key: string; label: string; unit: string; better: 'lower' | 'higher'; description: string };
export type Distribution = { median: number; p10: number; p90: number };
export type KpiValue = { key: string; value: number; distribution: Distribution | null; delta: number | null; status: 'better' | 'worse' | 'same' | null };
export type ProjectKpi = { project_id: string; project_name: string; target_launch_date: string; projected_finish: string | null; delay_days: number; on_target: boolean; on_target_probability: number | null };
export type MemberLoad = { resource_id: string; resource_name: string; demand_days: number; capacity_days: number; load_pct: number; overloaded: boolean };
export type Evaluation = { scenario_id: string | null; name: string; kpis: KpiValue[]; projects: ProjectKpi[]; members: MemberLoad[]; warnings: string[] };
export type CompareRequest = { scenario_ids: string[]; replications: number; seed?: number };
export type CompareResponse = { data_source: string; replications: number; baseline: Evaluation; scenarios: Evaluation[]; best_scenario_id: string | null; ranking: string[]; ranking_basis: string[] };

export const MAX_COMPARED_SCENARIOS = 5;

export const getKpiDefinitions = () => apiGet<KpiDefinition[]>('/evaluasi/kpi-definitions');
export const compareScenarios = (request: CompareRequest) => apiPost<CompareResponse>('/evaluasi/compare', request);
