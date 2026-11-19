/* Form scenario setup: nama, situasi, dan parameter (UC-01/UC-02, layar "Scenario setup" Tabel 4.7).
   PEMILIK: Orang 1 — Frontend. */

import type { Baseline, NewTask, Situation } from './api';
import { SITUATION_ORDER, SITUATIONS, type FieldSpec } from './situations';
import { Button } from '../../shared/ui';
import './scenarioForm.css';

export type Draft = { name: string; description: string; parameters: Record<string, unknown> & { situation: Situation } };

type Props = { baseline: Baseline; draft: Draft; onChange: (draft: Draft) => void };

/** Anggota lain dengan role utama yang sama dengan anggota `memberId` (calon pengganti). */
function sameRoleCandidates(baseline: Baseline, memberId: unknown): Baseline['resources'] {
  const member = baseline.resources.find((r) => r.resource_id === memberId);
  if (!member) return [];
  return baseline.resources.filter((r) => r.resource_id !== member.resource_id && r.primary_role_id === member.primary_role_id);
}

export function ScenarioForm({ baseline, draft, onChange }: Props) {
  const situation = draft.parameters.situation;
  const spec = SITUATIONS[situation];
  const setParam = (key: string, value: unknown) => {
    const parameters = { ...draft.parameters, [key]: value };
    // Task yang di-drop milik proyek lama tidak berlaku lagi setelah proyek diganti.
    if (situation === 'change_request' && key === 'project_id') parameters.remove_task_ids = [];
    // Pengganti harus tetap satu role dengan anggota; kosongkan jika anggota diganti dan pilihan lama tidak cocok.
    for (const f of spec.fields) {
      if (f.sameRoleAs !== key) continue;
      const stillValid = sameRoleCandidates(baseline, value).some((r) => r.resource_id === parameters[f.key]);
      if (!stillValid) parameters[f.key] = null;
    }
    // Pengganti otomatis dan pengganti manual saling meniadakan.
    if (key === 'auto_cover' && value) parameters.cover_resource_id = null;
    onChange({ ...draft, parameters });
  };
  const changeSituation = (next: Situation) => onChange({ ...draft, parameters: { situation: next, ...SITUATIONS[next].defaults(baseline) } });

  return <div className="sim-form">
    <div className="form-grid">
      <label className="field field-wide"><span>Nama skenario</span>
        <input value={draft.name} maxLength={120} required onChange={(e) => onChange({ ...draft, name: e.target.value })} />
      </label>
      <label className="field field-wide"><span>Situasi keputusan</span>
        <select value={situation} onChange={(e) => changeSituation(e.target.value as Situation)}>
          {SITUATION_ORDER.map((s) => <option key={s} value={s}>{SITUATIONS[s].label}</option>)}
        </select>
        <small>{spec.summary}</small>
      </label>
      {spec.fields.map((field) => <FieldInput key={field.key} field={field} baseline={baseline} value={draft.parameters[field.key]} params={draft.parameters} onChange={(v) => setParam(field.key, v)} />)}
      {situation === 'change_request' && <ChangeRequestEditor baseline={baseline} params={draft.parameters} setParam={setParam} />}
      <label className="field field-wide"><span>Catatan (opsional)</span>
        <textarea rows={2} maxLength={500} value={draft.description} onChange={(e) => onChange({ ...draft, description: e.target.value })} />
      </label>
    </div>
  </div>;
}

// ─── Satu input per FieldSpec ───────────────────────────────────────────────────

type FieldProps = { field: FieldSpec; baseline: Baseline; value: unknown; params: Draft['parameters']; onChange: (value: unknown) => void };

function FieldInput({ field, baseline, value, params, onChange }: FieldProps) {
  const text = value === null || value === undefined ? '' : String(value);
  const fromText = (raw: string) => (raw === '' && field.optional ? null : raw);
  const resources = field.sameRoleAs ? sameRoleCandidates(baseline, params[field.sameRoleAs]) : baseline.resources;
  // Jika "pilih pengganti otomatis" aktif, pilihan manual dinonaktifkan.
  const autoCover = field.key === 'cover_resource_id' && Boolean(params.auto_cover);
  let control;
  switch (field.kind) {
    case 'boolean':
      // Baris label kosong menjaga kotak toggle tetap sejajar dengan input di kolom sebelahnya.
      return <div className="field">
        <span aria-hidden="true">&nbsp;</span>
        <label className="field-check field-toggle"><input type="checkbox" checked={Boolean(value)} onChange={(e) => onChange(e.target.checked)} /><span>{field.label}</span></label>
        {field.hint && <small>{field.hint}</small>}
      </div>;
    case 'date':
      control = <input type="date" value={text} required={!field.optional} onChange={(e) => onChange(fromText(e.target.value))} />;
      break;
    case 'number':
      control = <input type="number" value={text} min={field.min} max={field.max} step={field.step} required={!field.optional} onChange={(e) => onChange(e.target.value === '' ? (field.optional ? null : '') : Number(e.target.value))} />;
      break;
    case 'text':
      control = <input value={text} required onChange={(e) => onChange(e.target.value)} />;
      break;
    default:
      control = <select value={text} disabled={autoCover} onChange={(e) => onChange(fromText(e.target.value))}>
        {field.optional && <option value="">—</option>}
        <EntityOptions kind={field.kind} baseline={baseline} choices={field.choices} resources={resources} />
      </select>;
  }
  const noCandidates = field.sameRoleAs !== undefined && resources.length === 0;
  const hint = autoCover ? 'Dipilih otomatis saat simulasi dijalankan.' : noCandidates ? 'Tidak ada anggota lain dengan role yang sama.' : field.hint;
  return <label className="field"><span>{field.label}</span>{control}{hint && <small>{hint}</small>}</label>;
}

function EntityOptions({ kind, baseline, choices, resources }: { kind: FieldSpec['kind']; baseline: Baseline; choices?: FieldSpec['choices']; resources: Baseline['resources'] }) {
  switch (kind) {
    case 'project': return <>{baseline.projects.map((p) => <option key={p.project_id} value={p.project_id}>{p.project_name}</option>)}</>;
    case 'resource': return <>{resources.map((r) => <option key={r.resource_id} value={r.resource_id}>{r.resource_name} ({r.primary_role_id})</option>)}</>;
    case 'role': return <>{baseline.roles.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}</>;
    case 'task': return <TaskOptions baseline={baseline} />;
    default: return <>{choices?.map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}</>;
  }
}

/** Hanya task yang belum selesai, dikelompokkan per proyek. */
function TaskOptions({ baseline, projectId }: { baseline: Baseline; projectId?: string }) {
  return <>{baseline.projects.filter((p) => !projectId || p.project_id === projectId).map((p) =>
    <optgroup key={p.project_id} label={p.project_name}>
      {baseline.tasks.filter((t) => t.project_id === p.project_id && t.status !== 'done').map((t) =>
        <option key={t.task_id} value={t.task_id}>{t.task_id} · {t.task_name}</option>)}
    </optgroup>)}</>;
}

// ─── Editor khusus change request: daftar task baru dan task yang dihapus ───────

type CrProps = { baseline: Baseline; params: Record<string, unknown>; setParam: (key: string, value: unknown) => void };

function ChangeRequestEditor({ baseline, params, setParam }: CrProps) {
  const tasks = (params.add_tasks as NewTask[] | undefined) ?? [];
  const removed = (params.remove_task_ids as string[] | undefined) ?? [];
  const projectId = params.project_id as string;
  const setTask = (i: number, patch: Partial<NewTask>) => setParam('add_tasks', tasks.map((t, j) => (j === i ? { ...t, ...patch } : t)));
  const blank: NewTask = { task_name: 'Task baru', required_role_id: baseline.roles[0]?.id ?? '', complexity_id: baseline.complexity_levels[0]?.id ?? '', estimated_days: 3, assignee_id: null, depends_on_task_ids: [] };

  return <>
    <fieldset className="field-wide sim-subform">
      <legend>Task yang ditambahkan</legend>
      {tasks.map((task, i) => <div className="sim-subform-row" key={i}>
        <label className="field"><span>Nama task</span><input value={task.task_name} onChange={(e) => setTask(i, { task_name: e.target.value })} /></label>
        <label className="field"><span>Role</span><select value={task.required_role_id} onChange={(e) => setTask(i, { required_role_id: e.target.value })}>{baseline.roles.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}</select></label>
        <label className="field"><span>Kompleksitas</span><select value={task.complexity_id} onChange={(e) => setTask(i, { complexity_id: e.target.value })}>{baseline.complexity_levels.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</select></label>
        <label className="field"><span>Estimasi (hari-orang)</span><input type="number" min={0.5} max={200} step={0.5} value={task.estimated_days} onChange={(e) => setTask(i, { estimated_days: Number(e.target.value) })} /></label>
        <label className="field"><span>Dikerjakan oleh</span><select value={task.assignee_id ?? ''} onChange={(e) => setTask(i, { assignee_id: e.target.value || null })}><option value="">Otomatis (role sama, beban terkecil)</option>{baseline.resources.map((r) => <option key={r.resource_id} value={r.resource_id}>{r.resource_name}</option>)}</select></label>
        <label className="field"><span>Setelah task</span><select value={task.depends_on_task_ids[0] ?? ''} onChange={(e) => setTask(i, { depends_on_task_ids: e.target.value ? [e.target.value] : [] })}><option value="">— tanpa dependency</option><TaskOptions baseline={baseline} projectId={projectId} /></select></label>
        <Button variant="danger" size="sm" onClick={() => setParam('add_tasks', tasks.filter((_, j) => j !== i))}>Hapus baris</Button>
      </div>)}
      <Button variant="outline" size="sm" onClick={() => setParam('add_tasks', [...tasks, blank])}>+ Tambah task</Button>
    </fieldset>
    <fieldset className="field-wide sim-subform">
      <legend>Task yang di-drop</legend>
      <div className="check-list">
        {baseline.tasks.filter((t) => t.project_id === projectId && t.status !== 'done').map((t) =>
          <label key={t.task_id} className="field-check"><input type="checkbox" checked={removed.includes(t.task_id)} onChange={(e) => setParam('remove_task_ids', e.target.checked ? [...removed, t.task_id] : removed.filter((id) => id !== t.task_id))} /><span>{t.task_id} · {t.task_name}</span></label>)}
      </div>
    </fieldset>
  </>;
}