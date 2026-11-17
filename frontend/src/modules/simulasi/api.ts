/* Klien API modul simulasi.
   PEMILIK: Orang 1 — Frontend. Tipe di file ini mencerminkan
   backend/app/modules/simulasi/schemas.py (Orang 2); ubah keduanya bersamaan. */

import { apiDelete, apiGet, apiPost, apiPut } from '../../shared/api/client';

// ─── Parameter skenario per situasi (Tabel 4.2 / 4.4) ───────────────────────────

export type Situation =
  | 'change_request' | 'member_absence' | 'new_member' | 'rotation'
  | 'task_overrun' | 'task_blocker' | 'priority_change' | 'critical_bug';

export type NewTask = {
  task_name: string; required_role_id: string; complexity_id: string; estimated_days: number;
  assignee_id: string | null; depends_on_task_ids: string[]; priority_rank?: number;
};
export type ChangeRequestParams = { situation: 'change_request'; project_id: string; request_date: string; add_tasks: NewTask[]; remove_task_ids: string[] };
export type MemberAbsenceParams = { situation: 'member_absence'; resource_id: string; date_start: string; date_end: string; absence_type: 'planned' | 'sudden'; cover_resource_id: string | null; auto_cover: boolean };
export type NewMemberParams = { situation: 'new_member'; resource_name: string; role_id: string; seniority: 'junior' | 'mid' | 'senior'; join_date: string; onboarding_days: number; initial_capacity: number; mentor_resource_id: string | null; mentor_overhead: number; project_id: string | null; assist_task_ids: string[] };
export type RotationParams = { situation: 'rotation'; resource_id: string; transfer_date: string; from_project_id: string; to_project_id: string | null; replacement_resource_id: string | null; auto_replacement: boolean };
export type TaskOverrunParams = { situation: 'task_overrun'; task_id: string; revised_estimated_days: number };
export type TaskBlockerParams = { situation: 'task_blocker'; task_id: string; block_start: string; block_days: number };
export type PriorityChangeParams = { situation: 'priority_change'; project_id: string; new_priority_rank: number | null; task_priorities: { task_id: string; priority_rank: number }[]; new_target_launch_date: string | null };
export type CriticalBugParams = { situation: 'critical_bug'; resource_id: string; report_date: string; fix_days: number; severity: 'critical' | 'high'; related_project_id: string | null };

export type ScenarioParameters =
  | ChangeRequestParams | MemberAbsenceParams | NewMemberParams | RotationParams
  | TaskOverrunParams | TaskBlockerParams | PriorityChangeParams | CriticalBugParams;

export type ScenarioInput = { name: string; description: string; parameters: ScenarioParameters };
export type Scenario = ScenarioInput & { scenario_id: string; data_source: string; created_at: string; updated_at: string };

// ─── Baseline untuk pilihan form ────────────────────────────────────────────────

export type Option = { id: string; name: string };
export type BaselineProject = { project_id: string; project_name: string; priority_rank: number; start_date: string; target_launch_date: string };
export type BaselineResource = { resource_id: string; resource_name: string; primary_role_id: string; secondary_role_ids: string[] };
export type BaselineTask = { task_id: string; project_id: string; task_name: string; required_role_id: string; complexity_id: string; estimated_days: number; status: string; assignee_ids: string[] };
export type Baseline = { data_source: string; start_date: string; as_of: string | null; notes: string[]; projects: BaselineProject[]; resources: BaselineResource[]; tasks: BaselineTask[]; roles: Option[]; complexity_levels: Option[] };

// ─── Hasil simulasi (FR-04) ─────────────────────────────────────────────────────

export type ProjectOutcome = { project_id: string; project_name: string; target_launch_date: string; baseline_finish: string | null; scenario_finish: string | null; shift_days: number | null };
export type TaskChange = { task_id: string; project_id: string; task_name: string; change: 'added' | 'removed' | 'shifted' | 'unchanged'; baseline_start: string | null; baseline_finish: string | null; scenario_start: string | null; scenario_finish: string | null; shift_days: number | null };
export type WeeklyLoad = { week_start: string; capacity: number; used: number };
export type ResourceLoad = { resource_id: string; resource_name: string; baseline: WeeklyLoad[]; scenario: WeeklyLoad[] };
export type SimulationRun = { scenario: Scenario; data_source: string; projects: ProjectOutcome[]; tasks: TaskChange[]; resource_load: ResourceLoad[]; warnings: string[] };

// ─── Endpoint (backend/app/modules/simulasi/router.py) ──────────────────────────

export const getBaseline = () => apiGet<Baseline>('/simulasi/baseline');
export const listScenarios = () => apiGet<Scenario[]>('/simulasi/scenarios');
export const createScenario = (input: ScenarioInput) => apiPost<Scenario>('/simulasi/scenarios', input);
export const updateScenario = (id: string, input: ScenarioInput) => apiPut<Scenario>(`/simulasi/scenarios/${id}`, input);
export const deleteScenario = (id: string) => apiDelete(`/simulasi/scenarios/${id}`);
export const duplicateScenario = (id: string) => apiPost<Scenario>(`/simulasi/scenarios/${id}/duplicate`);
export const runScenario = (id: string) => apiPost<SimulationRun>(`/simulasi/scenarios/${id}/run`);
