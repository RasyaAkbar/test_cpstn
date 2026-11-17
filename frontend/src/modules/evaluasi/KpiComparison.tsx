/* Tabel perbandingan KPI baseline vs skenario, penanda nilai lebih buruk, indikator
   skenario terbaik, Schedule Variance per proyek, beban per anggota (RLI/SOI), dan task
   dengan Cascade Delay Impact terbesar (FR-04.1 s.d. FR-04.10, FR-06, Tabel 4.7).
   peringkat skenario, ketepatan target per proyek, dan beban per anggota (FR-06, Tabel 4.7).
   PEMILIK: Orang 1 — Frontend. Definisi dan arah KPI datang dari backend (Orang 3). */

import type { CompareResponse, Evaluation, KpiDefinition, KpiValue, TaskCascade } from './api';
import { formatDate, formatNumber, formatSigned } from '../../shared/format';

type Props = { result: CompareResponse; definitions: KpiDefinition[] };

const STATUS_LABEL = { better: 'lebih baik', worse: 'lebih buruk', same: 'sama' } as const;
const columnKey = (c: Evaluation) => c.scenario_id ?? 'baseline';

export function KpiComparison({ result, definitions }: Props) {
  const columns = [result.baseline, ...result.scenarios];
  const best = result.scenarios.find((s) => s.scenario_id === result.best_scenario_id);
  const withRange = result.replications > 0;
  const threshold = formatNumber(result.overload_threshold);

  return <>
    <section className="module-panel" aria-label="Perbandingan KPI">
      <div className="panel-heading">
        <h2>Perbandingan KPI</h2>
        <span className="subtle-badge">Data {result.data_source === 'synthetic' ? 'sintetis' : 'PuTI'} · {withRange ? `${result.replications} replikasi` : 'estimasi tunggal'} · threshold RLI {threshold}</span>
      </div>
      {best && <div className="eval-best">
        <strong>Skenario terbaik: {best.name}</strong>
        <p>Diurutkan berdasarkan {result.ranking_basis.join(' → ')}. Skenario terbaik adalah yang paling kecil dampaknya; keputusan tetap di Kepala Seksi dan System Analyst.</p>
      </div>}
      <div className="table-scroll"><table className="data-table kpi-table">
        <thead><tr><th>KPI</th>{columns.map((c) => <th key={columnKey(c)} className={c.scenario_id === result.best_scenario_id ? 'is-best' : ''}>
          {c.name}{c.scenario_id === result.best_scenario_id && <span className="pill pill-success">Terbaik</span>}
        </th>)}</tr></thead>
        <tbody>{definitions.map((def) => <tr key={def.key}>
          <th scope="row" title={def.description}>{def.label}<small>{def.fr} · {def.unit} · {def.better === 'lower' ? 'makin kecil makin baik' : 'makin besar makin baik'}</small></th>
          {columns.map((c) => <KpiCell key={columnKey(c)} value={c.kpis.find((k) => k.key === def.key)} best={c.scenario_id === result.best_scenario_id} />)}
        </tr>)}</tbody>
      </table></div>
      <p className="text-caption eval-footnote">Nilai utama memakai sisa estimasi effort dari data. {withRange ? 'Baris kecil menampilkan median dan rentang P10–P90 dari replikasi, karena hasil simulasi bersifat acak.' : 'Peluang launch tepat waktu butuh replikasi > 0.'} Delta = skenario − baseline. Arahkan kursor ke nama KPI untuk melihat rumusnya.</p>
    </section>

    <section className="module-panel" aria-label="Schedule Variance per proyek">
      <div className="panel-heading"><h2>Launch per proyek (Schedule Variance)</h2></div>
      <div className="table-scroll"><table className="data-table">
        <thead><tr><th>Proyek</th><th>Target</th>{columns.map((c) => <th key={columnKey(c)}>{c.name}</th>)}</tr></thead>
        <tbody>{result.baseline.projects.map((p) => <tr key={p.project_id}>
          <td>{p.project_name}</td>
          <td>{formatDate(p.target_launch_date)}</td>
          {columns.map((c) => <ProjectCell key={columnKey(c)} evaluation={c} projectId={p.project_id} />)}
        </tr>)}</tbody>
      </table></div>
      <p className="text-caption eval-footnote">SV = launch hasil simulasi − target, dalam hari kerja. Positif = terlambat.</p>
    </section>

    <section className="module-panel" aria-label="Beban per anggota">
      <div className="panel-heading"><h2>Beban anggota (Resource Load Index)</h2></div>
      <div className="table-scroll"><table className="data-table">
        <thead><tr><th>Anggota</th>{columns.map((c) => <th key={columnKey(c)} className="num">{c.name}</th>)}</tr></thead>
        <tbody>{memberIds(columns).map(([id, name]) => <tr key={id}>
          <td>{name}</td>
          {columns.map((c) => {
            const m = c.members.find((x) => x.resource_id === id);
            return <td key={columnKey(c)} className={`num ${m && m.soi > 0 ? 'cell-danger' : ''}`}
              title={m ? `Rata-rata RLI ${formatNumber(m.rli_mean)} · ${m.overload_weeks} minggu overload · Blocked ${formatNumber(m.blocked_ratio)}% · Reallocated ${formatNumber(m.reallocated_ratio)}%` : undefined}>
              {m ? <>RLI puncak {formatNumber(m.rli_peak)}{m.soi > 0 && <small>SOI {formatNumber(m.soi)}</small>}</> : '—'}
            </td>;
          })}
        </tr>)}</tbody>
      </table></div>
      <p className="text-caption eval-footnote">RLI di atas {threshold} = overload (FR-04.4). Sel merah = overload minimal 2 minggu berturut-turut (SOI &gt; 0, FR-04.6). Arahkan kursor untuk rata-rata RLI dan rasio waktu tunggu (FR-04.10).</p>
    </section>

    <section className="module-panel" aria-label="Cascade Delay Impact">
      <div className="panel-heading"><h2>Task dengan dampak berantai terbesar (CDI)</h2></div>
      <CascadeTable columns={columns} />
      <p className="text-caption eval-footnote">CDI = keterlambatan task × jumlah faktor propagasi ke task hilir (hard 1.0, soft 0.3), dalam hari kerja (FR-04.7). Menangani task teratas lebih dulu mengurangi keterlambatan berantai paling banyak.</p>
    </section>
  </>;
}

function KpiCell({ value, best }: { value: KpiValue | undefined; best: boolean }) {
  if (!value) return <td>—</td>;
  const d = value.distribution;
  return (
    <td className={`num ${best ? 'is-best' : ''} ${value.status === 'worse' ? 'cell-danger' : ''}`}>
      <strong>{formatNumber(value.value)}</strong>
      {value.delta !== null && value.status && value.status !== 'same' && (
        <span className={`delta delta-${value.status}`} title={STATUS_LABEL[value.status]}>
          {' '}{formatSigned(value.delta)}
        </span>
      )}
      {d && <small>median {formatNumber(d.median)} · {formatNumber(d.p10)}–{formatNumber(d.p90)}</small>}
    </td>
  );
}

function ProjectCell({ evaluation, projectId }: { evaluation: Evaluation; projectId: string }) {
  const p = evaluation.projects.find((x) => x.project_id === projectId);
  if (!p) return <td>—</td>;
  return <td className={p.on_target ? '' : 'cell-danger'}>
    {formatDate(p.projected_finish)}
    {p.sv_days !== 0 && <span className={`delta delta-${p.sv_days > 0 ? 'worse' : 'better'}`}> SV {formatSigned(p.sv_days)} hari kerja</span>}
    {p.on_target_probability !== null && <small>Peluang tepat waktu {Math.round(p.on_target_probability * 100)}%</small>}
  </td>;
}

function CascadeTable({ columns }: { columns: Evaluation[] }) {
  const tasks = new Map<string, TaskCascade>();
  columns.forEach((c) => c.cascade.forEach((t) => { if (!tasks.has(t.task_id)) tasks.set(t.task_id, t); }));
  const top = [...tasks.values()].sort((a, b) => b.cdi - a.cdi).slice(0, 10);
  if (top.length === 0) return <p className="text-caption eval-footnote">Tidak ada task terlambat yang punya task hilir.</p>;
  return <div className="table-scroll"><table className="data-table">
    <thead><tr><th>Task</th><th>Proyek</th><th className="num">Task hilir</th>{columns.map((c) => <th key={columnKey(c)} className="num">{c.name}</th>)}</tr></thead>
    <tbody>{top.map((t) => <tr key={t.task_id}>
      <td><span className="text-data">{t.task_id}</span> {t.task_name}</td>
      <td>{t.project_id}</td>
      <td className="num">{t.downstream_tasks}</td>
      {columns.map((c) => {
        const row = c.cascade.find((x) => x.task_id === t.task_id);
        return <td key={columnKey(c)} className="num" title={row ? `Terlambat ${row.delay_days} hari kerja dari rencana` : 'Di luar 10 besar'}>{row ? formatNumber(row.cdi) : '—'}</td>;
      })}
    </tr>)}</tbody>
  </table></div>;
}

/** Semua anggota yang muncul di baseline atau skenario (skenario anggota baru menambah baris). */
function memberIds(columns: Evaluation[]): [string, string][] {
  const seen = new Map<string, string>();
  columns.forEach((c) => c.members.forEach((m) => seen.set(m.resource_id, m.resource_name)));
  return [...seen.entries()];
}
