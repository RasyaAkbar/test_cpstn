/* Label, penjelasan, field form, dan nilai awal untuk 8 situasi keputusan (Tabel 4.2).
   PEMILIK: Orang 1 — Frontend. Key field harus sama dengan nama field di
   backend/app/modules/simulasi/schemas.py. */

import type { Baseline, Situation } from './api';
import { addDays } from '../../shared/format';

export type FieldKind = 'project' | 'resource' | 'task' | 'role' | 'date' | 'number' | 'text' | 'boolean' | 'choice';

export type FieldSpec = {
  key: string;
  label: string;
  kind: FieldKind;
  optional?: boolean; // tampilkan opsi kosong; nilai kosong dikirim sebagai null
  min?: number; max?: number; step?: number;
  choices?: readonly { value: string; label: string }[];
  hint?: string;
};

type SituationSpec = {
  label: string;
  summary: string;
  fields: readonly FieldSpec[];
  defaults: (b: Baseline) => Record<string, unknown>;
};

export const SITUATION_ORDER: readonly Situation[] = [
  'change_request', 'member_absence', 'new_member', 'rotation',
  'task_overrun', 'task_blocker', 'priority_change', 'critical_bug',
];

const firstOpenTask = (b: Baseline) => b.tasks.find((t) => t.status !== 'done') ?? b.tasks[0];

export const SITUATIONS: Record<Situation, SituationSpec> = {
  change_request: {
    label: 'Change request mid-sprint',
    summary: 'Tambah atau hapus task pada proyek setelah sprint berjalan.',
    fields: [
      { key: 'project_id', label: 'Proyek', kind: 'project' },
      { key: 'request_date', label: 'Tanggal CR', kind: 'date' },
    ],
    defaults: (b) => ({
      project_id: b.projects[0]?.project_id, request_date: addDays(b.start_date, 7), remove_task_ids: [],
      add_tasks: [{ task_name: 'Fitur tambahan', required_role_id: b.roles[0]?.id, complexity_id: (b.complexity_levels[1] ?? b.complexity_levels[0])?.id, estimated_days: 3, assignee_id: null, depends_on_task_ids: [] }],
    }),
  },
  member_absence: {
    label: 'Anggota absen',
    summary: 'Cuti terencana atau mendadak, dengan atau tanpa pengganti role sama.',
    fields: [
      { key: 'resource_id', label: 'Anggota', kind: 'resource' },
      { key: 'date_start', label: 'Mulai absen', kind: 'date' },
      { key: 'date_end', label: 'Selesai absen', kind: 'date' },
      { key: 'absence_type', label: 'Jenis', kind: 'choice', choices: [{ value: 'sudden', label: 'Mendadak' }, { value: 'planned', label: 'Terencana' }] },
      { key: 'cover_resource_id', label: 'Pengganti', kind: 'resource', optional: true },
      { key: 'auto_cover', label: 'Pilih pengganti otomatis', kind: 'boolean', hint: 'Anggota role sama dengan beban terkecil' },
    ],
    defaults: (b) => ({ resource_id: b.resources[0]?.resource_id, date_start: addDays(b.start_date, 7), date_end: addDays(b.start_date, 18), absence_type: 'sudden', cover_resource_id: null, auto_cover: false }),
  },
  new_member: {
    label: 'Anggota baru',
    summary: 'Anggota baru bergabung dengan masa onboarding dan waktu mentor.',
    fields: [
      { key: 'resource_name', label: 'Nama (pseudonim)', kind: 'text' },
      { key: 'role_id', label: 'Role', kind: 'role' },
      { key: 'seniority', label: 'Senioritas', kind: 'choice', choices: [{ value: 'junior', label: 'Junior' }, { value: 'mid', label: 'Mid' }, { value: 'senior', label: 'Senior' }] },
      { key: 'join_date', label: 'Tanggal bergabung', kind: 'date' },
      { key: 'project_id', label: 'Membantu proyek', kind: 'project', hint: 'Task role sama di proyek ini' },
      { key: 'onboarding_days', label: 'Lama onboarding (hari kerja)', kind: 'number', min: 0, max: 60, step: 1 },
      { key: 'initial_capacity', label: 'Kapasitas awal (0–1)', kind: 'number', min: 0, max: 1, step: 0.05 },
      { key: 'mentor_resource_id', label: 'Mentor', kind: 'resource', optional: true },
      { key: 'mentor_overhead', label: 'Waktu mentor per hari (0–0,5)', kind: 'number', min: 0, max: 0.5, step: 0.05 },
    ],
    defaults: (b) => ({ resource_name: 'Anggota baru', role_id: b.roles[0]?.id, seniority: 'junior', join_date: addDays(b.start_date, 7), onboarding_days: 10, initial_capacity: 0.3, mentor_resource_id: null, mentor_overhead: 0.1, project_id: b.projects[0]?.project_id, assist_task_ids: [] }),
  },
  rotation: {
    label: 'Rotasi atau penarikan',
    summary: 'Anggota pindah ke proyek lain, atau keluar dari unit jika tujuan kosong.',
    fields: [
      { key: 'resource_id', label: 'Anggota', kind: 'resource' },
      { key: 'transfer_date', label: 'Tanggal pindah', kind: 'date' },
      { key: 'from_project_id', label: 'Dari proyek', kind: 'project' },
      { key: 'to_project_id', label: 'Ke proyek', kind: 'project', optional: true, hint: 'Kosong = keluar dari unit' },
      { key: 'replacement_resource_id', label: 'Pengganti', kind: 'resource', optional: true },
      { key: 'auto_replacement', label: 'Pilih pengganti otomatis', kind: 'boolean' },
    ],
    defaults: (b) => ({ resource_id: b.resources[0]?.resource_id, transfer_date: addDays(b.start_date, 14), from_project_id: b.projects[0]?.project_id, to_project_id: null, replacement_resource_id: null, auto_replacement: true }),
  },
  task_overrun: {
    label: 'Task overrun',
    summary: 'Estimasi task ternyata lebih besar dari rencana.',
    fields: [
      { key: 'task_id', label: 'Task', kind: 'task' },
      { key: 'revised_estimated_days', label: 'Estimasi baru (hari-orang)', kind: 'number', min: 0.5, max: 200, step: 0.5 },
    ],
    defaults: (b) => { const t = firstOpenTask(b); return { task_id: t?.task_id, revised_estimated_days: Math.round((t?.estimated_days ?? 4) * 1.5) }; },
  },
  task_blocker: {
    label: 'Task blocker',
    summary: 'Task tertahan beberapa hari kerja; anggota beralih ke task lain.',
    fields: [
      { key: 'task_id', label: 'Task', kind: 'task' },
      { key: 'block_start', label: 'Mulai tertahan', kind: 'date' },
      { key: 'block_days', label: 'Lama tertahan (hari kerja)', kind: 'number', min: 1, max: 120, step: 1 },
    ],
    defaults: (b) => ({ task_id: firstOpenTask(b)?.task_id, block_start: addDays(b.start_date, 2), block_days: 5 }),
  },
  priority_change: {
    label: 'Perubahan prioritas',
    summary: 'Process owner menaikkan atau menurunkan prioritas proyek, atau menggeser target.',
    fields: [
      { key: 'project_id', label: 'Proyek', kind: 'project' },
      { key: 'new_priority_rank', label: 'Peringkat prioritas baru (1 = tertinggi)', kind: 'number', min: 1, step: 1, optional: true },
      { key: 'new_target_launch_date', label: 'Target launch baru', kind: 'date', optional: true },
    ],
    defaults: (b) => ({ project_id: b.projects.at(-1)?.project_id, new_priority_rank: 1, task_priorities: [], new_target_launch_date: null }),
  },
  critical_bug: {
    label: 'Bug kritis',
    summary: 'Hotfix mendahului pekerjaan fitur anggota yang ditugaskan.',
    fields: [
      { key: 'resource_id', label: 'Anggota yang memperbaiki', kind: 'resource' },
      { key: 'report_date', label: 'Tanggal laporan', kind: 'date' },
      { key: 'fix_days', label: 'Effort perbaikan (hari-orang)', kind: 'number', min: 0.5, max: 60, step: 0.5 },
      { key: 'severity', label: 'Tingkat', kind: 'choice', choices: [{ value: 'critical', label: 'Kritis' }, { value: 'high', label: 'Tinggi' }] },
      { key: 'related_project_id', label: 'Proyek terkait', kind: 'project', optional: true },
    ],
    defaults: (b) => ({ resource_id: b.resources[0]?.resource_id, report_date: addDays(b.start_date, 3), fix_days: 3, severity: 'critical', related_project_id: null }),
  },
};
