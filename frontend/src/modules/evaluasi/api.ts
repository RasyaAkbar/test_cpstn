/* Klien API modul evaluasi (KPI).
   PEMILIK: Orang 1 — Frontend. Tipe di file ini mencerminkan
   backend/app/modules/evaluasi/schemas.py (Orang 3); ubah keduanya bersamaan. */

import { apiGet, apiPost } from '../../shared/api/client';

export type KpiDefinition = { key: string; fr: string; label: string; unit: string; better: 'lower' | 'higher'; description: string };
export type Distribution = { median: number; p10: number; p90: number };
export type KpiValue = { key: string; value: number | null; distribution: Distribution | null; delta: number | null; status: 'better' | 'worse' | 'same' | null };
export type ProjectKpi = { project_id: string; project_name: string; target_launch_date: string; projected_finish: string | null; sv_days: number; on_target: boolean; on_target_probability: number | null };
export type MemberKpi = {
  resource_id: string; resource_name: string; role_id: string;
  weekly_rli: (number | null)[]; rli_peak: number; rli_mean: number; overload_weeks: number; soi: number;
  blocked_ratio: number | null; reallocated_ratio: number | null;
};
export type TaskCascade = { task_id: string; task_name: string; project_id: string; delay_days: number; downstream_tasks: number; cdi: number };
export type Evaluation = { scenario_id: string | null; name: string; kpis: KpiValue[]; projects: ProjectKpi[]; members: MemberKpi[]; cascade: TaskCascade[]; week_starts: string[]; warnings: string[] };
export type CompareRequest = { scenario_ids: string[]; replications: number; seed?: number; overload_threshold?: number };
export type CompareResponse = { data_source: string; replications: number; overload_threshold: number; baseline: Evaluation; scenarios: Evaluation[]; best_scenario_id: string | null; ranking: string[]; ranking_basis: string[] };

export type GroupRatio = { key: string; label: string; value: number | null; tasks: number };
export type Historical = {
  data_source: string; as_of: string | null; notes: string[];
  ear: number | null; ear_by_complexity: GroupRatio[]; ear_by_role: GroupRatio[];
  rework_rate: number | null; rework_by_role: GroupRatio[]; rework_by_project: GroupRatio[];
};

export const MAX_COMPARED_SCENARIOS = 5;

export const getKpiDefinitions = () => apiGet<KpiDefinition[]>('/evaluasi/kpi-definitions');
export const compareScenarios = (request: CompareRequest) => apiPost<CompareResponse>('/evaluasi/compare', request);
export const getHistorical = () => apiGet<Historical>('/evaluasi/historical');
