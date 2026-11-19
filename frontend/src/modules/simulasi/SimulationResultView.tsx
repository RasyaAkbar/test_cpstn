import { useState } from 'react';
import { Link } from 'react-router-dom';
import type { SimulationRun, TaskChange, WeeklyLoad } from './api';
import type { Evaluation, KpiDefinition } from '../evaluasi/api';
import { daysBetween, formatDate, formatNumber, formatSigned } from '../../shared/format';

type Props = { run: SimulationRun; kpis: Evaluation | null; definitions: KpiDefinition[] };

const SUMMARY_KPIS = ['projects_late', 'sv_total_days', 'sustained_overload_resources', 'blocked_ratio'];
const CHANGE_LABEL: Record<TaskChange['change'], string> = { added: 'Baru', removed: 'Di-drop', shifted: 'Bergeser', unchanged: 'Tetap' };

export function SimulationResultView({ run, kpis, definitions }: Props) {
  return <div className="sim-result">
    {run.warnings.length > 0 && <ul className="notice notice-warning">{run.warnings.map((w) => <li key={w}>{w}</li>)}</ul>}
    {kpis && <KpiSummary kpis={kpis} definitions={definitions} scenarioId={run.scenario.scenario_id} />}
    <ProjectTable run={run} />
    <ScheduleTable tasks={run.tasks} />
    <LoadHeatmap run={run} />
  </div>;
}

// ─── Ringkasan KPI (F2: "show the KPIs it produces") ────────────────────────────

function KpiSummary({ kpis, definitions, scenarioId }: { kpis: Evaluation; definitions: KpiDefinition[]; scenarioId: string }) {
  return <section className="result-block">
    <div className="result-heading"><h3>Ringkasan KPI</h3><Link className="button button-ghost" to={`/evaluasi?scenarios=${scenarioId}`}>Bandingkan di Evaluasi</Link></div>
    <div className="metric-grid">
      {SUMMARY_KPIS.map((key, i) => {
        const value = kpis.kpis.find((k) => k.key === key);
        const def = definitions.find((d) => d.key === key);
        if (!value || !def) return null;
        return <article key={key} className={`metric-card metric-${i}`} title={def.description}>
          <h2>{def.label}</h2>
          <strong>{formatNumber(value.value)} <small className="text-caption">{def.unit}</small></strong>
          <p className={`delta delta-${value.status ?? 'same'}`}>{formatSigned(value.delta)} vs baseline</p>
        </article>;
      })}
    </div>
  </section>;
}

// ─── Proyek terdampak ───────────────────────────────────────────────────────────

function ProjectTable({ run }: { run: SimulationRun }) {
  return <section className="result-block">
    <h3>Proyek terdampak</h3>
    <div className="table-scroll"><table className="data-table">
      <thead><tr><th>Proyek</th><th>Target launch</th><th>Selesai (baseline)</th><th>Selesai (skenario)</th><th>Pergeseran</th><th>Target</th></tr></thead>
      <tbody>{run.projects.map((p) => {
        const late = p.scenario_finish === null || p.scenario_finish > p.target_launch_date;
        return <tr key={p.project_id}>
          <td>{p.project_name}</td>
          <td>{formatDate(p.target_launch_date)}</td>
          <td>{formatDate(p.baseline_finish)}</td>
          <td>{formatDate(p.scenario_finish)}</td>
          <td className={`num delta delta-${shiftStatus(p.shift_days)}`}>{formatSigned(p.shift_days)} hari</td>
          <td><span className={`pill ${late ? 'pill-danger' : 'pill-success'}`}>{late ? 'Terlewat' : 'Tercapai'}</span></td>
        </tr>;
      })}</tbody>
    </table></div>
  </section>;
}

const shiftStatus = (shift: number | null) => (shift === null || shift === 0 ? 'same' : shift > 0 ? 'worse' : 'better');

// ─── Jadwal skenario vs baseline (Gantt sederhana) ──────────────────────────────

function ScheduleTable({ tasks }: { tasks: TaskChange[] }) {
  const [onlyChanged, setOnlyChanged] = useState(true);
  const rows = onlyChanged ? tasks.filter((t) => t.change !== 'unchanged') : tasks;
  // Skala linimasa mengikuti task yang sedang ditampilkan (bukan seluruh proyek),
  // supaya bar tidak mengecil jadi titik saat hanya task yang berubah yang ditampilkan.
  const dates = rows.flatMap((t) => [t.baseline_start, t.baseline_finish, t.scenario_start, t.scenario_finish]).filter((d): d is string => d !== null).sort();
  const first = dates[0];
  const last = dates[dates.length - 1];
  const span = first ? daysBetween(first, last) + 1 : 1;
  const bar = (start: string | null, finish: string | null) => {
    if (!first || !start || !finish) return undefined;
    return { left: `${(daysBetween(first, start) / span) * 100}%`, width: `${Math.max(((daysBetween(start, finish) + 1) / span) * 100, 0.8)}%` };
  };

  return <section className="result-block">
    <div className="result-heading">
      <h3>Jadwal skenario vs baseline</h3>
      <label className="field-check"><input type="checkbox" checked={onlyChanged} onChange={(e) => setOnlyChanged(e.target.checked)} /><span>Hanya task yang berubah</span></label>
    </div>
    <p className="legend"><span className="legend-bar legend-baseline" />Baseline <span className="legend-bar legend-scenario" />Skenario {first && <>· Rentang linimasa {formatDate(first)} – {formatDate(last)}</>}</p>
    {rows.length === 0 ? <p className="text-caption">Tidak ada task yang bergeser.</p> :
      <div className="table-scroll"><table className="data-table gantt-table">
        <thead><tr><th>Task</th><th>Status</th><th>Selesai (baseline → skenario)</th><th className="gantt-col">Linimasa</th></tr></thead>
        <tbody>{rows.map((t) => <tr key={t.task_id}>
          <td><span className="text-data">{t.task_id}</span> {t.task_name}</td>
          <td><span className={`pill pill-${t.change}`}>{CHANGE_LABEL[t.change]}</span></td>
          <td>{formatDate(t.baseline_finish)} → {formatDate(t.scenario_finish)} {t.shift_days ? <span className={`delta delta-${shiftStatus(t.shift_days)}`}>({formatSigned(t.shift_days)})</span> : null}</td>
          <td className="gantt-col"><div className="gantt-track">
            {bar(t.baseline_start, t.baseline_finish) && <span className="gantt-bar gantt-baseline" style={bar(t.baseline_start, t.baseline_finish)} />}
            {bar(t.scenario_start, t.scenario_finish) && <span className="gantt-bar gantt-scenario" style={bar(t.scenario_start, t.scenario_finish)} />}
          </div></td>
        </tr>)}</tbody>
      </table></div>}
  </section>;
}

// ─── Beban anggota per minggu ───────────────────────────────────────────────────

const utilisation = (w: WeeklyLoad | undefined) => (w && w.capacity > 0 ? Math.round((w.used / w.capacity) * 100) : null);
const heatLevel = (pct: number | null) => (pct === null ? 'none' : pct >= 90 ? 'high' : pct >= 50 ? 'mid' : pct > 0 ? 'low' : 'zero');

function LoadHeatmap({ run }: { run: SimulationRun }) {
  const weeks = run.resource_load[0]?.scenario.map((w) => w.week_start) ?? [];
  return <section className="result-block">
    <h3>Beban anggota per minggu (skenario)</h3>
    <p className="text-caption">Persentase kapasitas terpakai. Arahkan kursor untuk melihat nilai baseline. Sel kosong = tidak ada kapasitas (libur, cuti, belum bergabung).</p>
    <div className="table-scroll"><table className="data-table heatmap">
      <thead><tr><th>Anggota</th>{weeks.map((w) => <th key={w} className="num">{formatDate(w).replace(/ \d{4}$/, '')}</th>)}</tr></thead>
      <tbody>{run.resource_load.map((r) => <tr key={r.resource_id}>
        <td>{r.resource_name}</td>
        {r.scenario.map((w, i) => {
          const pct = utilisation(w);
          const base = utilisation(r.baseline[i]);
          return <td key={w.week_start} className={`num heat heat-${heatLevel(pct)}`} title={`Skenario ${pct ?? '—'}% · Baseline ${base ?? '—'}% · ${formatNumber(w.used)}/${formatNumber(w.capacity)} hari-orang`}>{pct ?? ''}</td>;
        })}
      </tr>)}</tbody>
    </table></div>
  </section>;
}