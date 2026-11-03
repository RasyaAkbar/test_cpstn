/* Tabel perbandingan KPI baseline vs skenario, penanda nilai lebih buruk, indikator
   skenario terbaik, ketepatan target per proyek, dan beban per anggota (FR-06, Tabel 4.7).
   PEMILIK: Orang 1 — Frontend. Definisi dan arah KPI datang dari backend (Orang 3). */

import type { CompareResponse, Evaluation, KpiDefinition, KpiValue } from './api';
import { formatDate, formatNumber, formatSigned } from '../../shared/format';

type Props = { result: CompareResponse; definitions: KpiDefinition[] };

const STATUS_LABEL = { better: 'lebih baik', worse: 'lebih buruk', same: 'sama' } as const;

export function KpiComparison({ result, definitions }: Props) {
  const columns = [result.baseline, ...result.scenarios];
  const best = result.scenarios.find((s) => s.scenario_id === result.best_scenario_id);
  const withRange = result.replications > 0;

  return <>
    <section className="module-panel" aria-label="Perbandingan KPI">
      <div className="panel-heading">
        <h2>Perbandingan KPI</h2>
        <span className="subtle-badge">Data {result.data_source === 'synthetic' ? 'sintetis' : 'PuTI'} · {withRange ? `${result.replications} replikasi` : 'estimasi tunggal'}</span>
      </div>
      {best && <div className="eval-best">
        <strong>Skenario terbaik: {best.name}</strong>
        <p>Diurutkan berdasarkan {result.ranking_basis.join(' → ')}. Skenario terbaik adalah yang paling kecil dampaknya; keputusan tetap di Kepala Seksi dan System Analyst.</p>
      </div>}
      <div className="table-scroll"><table className="data-table kpi-table">
        <thead><tr><th>KPI</th>{columns.map((c) => <th key={c.scenario_id ?? 'baseline'} className={c.scenario_id === result.best_scenario_id ? 'is-best' : ''}>
          {c.name}{c.scenario_id === result.best_scenario_id && <span className="pill pill-success">Terbaik</span>}
        </th>)}</tr></thead>
        <tbody>{definitions.map((def) => <tr key={def.key}>
          <th scope="row" title={def.description}>{def.label}<small>{def.unit} · {def.better === 'lower' ? 'makin kecil makin baik' : 'makin besar makin baik'}</small></th>
          {columns.map((c) => <KpiCell key={c.scenario_id ?? 'baseline'} value={c.kpis.find((k) => k.key === def.key)} best={c.scenario_id === result.best_scenario_id} />)}
        </tr>)}</tbody>
      </table></div>
      <p className="text-caption eval-footnote">Nilai utama memakai estimasi effort dari data. {withRange && 'Baris kecil menampilkan median dan rentang P10–P90 dari replikasi, karena hasil simulasi bersifat acak.'} Delta = skenario − baseline.</p>
    </section>

    <section className="module-panel" aria-label="Target launch per proyek">
      <div className="panel-heading"><h2>Target launch per proyek</h2></div>
      <div className="table-scroll"><table className="data-table">
        <thead><tr><th>Proyek</th><th>Target</th>{columns.map((c) => <th key={c.scenario_id ?? 'baseline'}>{c.name}</th>)}</tr></thead>
        <tbody>{result.baseline.projects.map((p) => <tr key={p.project_id}>
          <td>{p.project_name}</td>
          <td>{formatDate(p.target_launch_date)}</td>
          {columns.map((c) => <ProjectCell key={c.scenario_id ?? 'baseline'} evaluation={c} projectId={p.project_id} />)}
        </tr>)}</tbody>
      </table></div>
    </section>

    <section className="module-panel" aria-label="Beban per anggota">
      <div className="panel-heading"><h2>Beban anggota terhadap kapasitas</h2></div>
      <div className="table-scroll"><table className="data-table">
        <thead><tr><th>Anggota</th>{columns.map((c) => <th key={c.scenario_id ?? 'baseline'} className="num">{c.name}</th>)}</tr></thead>
        <tbody>{memberIds(columns).map(([id, name]) => <tr key={id}>
          <td>{name}</td>
          {columns.map((c) => {
            const m = c.members.find((x) => x.resource_id === id);
            return <td key={c.scenario_id ?? 'baseline'} className={`num ${m?.overloaded ? 'cell-danger' : ''}`} title={m ? `${formatNumber(m.demand_days)} / ${formatNumber(m.capacity_days)} hari-orang` : undefined}>
              {m ? `${formatNumber(m.load_pct)}%` : '—'}
            </td>;
          })}
        </tr>)}</tbody>
      </table></div>
      <p className="text-caption eval-footnote">Beban = pekerjaan anggota / kapasitasnya sampai target proyek terakhir yang ia kerjakan. Di atas 100% = overload.</p>
    </section>
  </>;
}

function KpiCell({ value, best }: { value: KpiValue | undefined; best: boolean }) {
  if (!value) return <td>—</td>;
  const d = value.distribution;
  return <td className={`num ${best ? 'is-best' : ''} ${value.status === 'worse' ? 'cell-danger' : ''}`}>
    <strong>{formatNumber(value.value)}</strong>
    {value.delta !== null && value.status && value.status !== 'same' && <span className={`delta delta-${value.status}`} title={STATUS_LABEL[value.status]}> {formatSigned(value.delta)}</span>}
    {d && <small>median {formatNumber(d.median)} · {formatNumber(d.p10)}–{formatNumber(d.p90)}</small>}
  </td>;
}

function ProjectCell({ evaluation, projectId }: { evaluation: Evaluation; projectId: string }) {
  const p = evaluation.projects.find((x) => x.project_id === projectId);
  if (!p) return <td>—</td>;
  return <td className={p.on_target ? '' : 'cell-danger'}>
    {formatDate(p.projected_finish)}{p.delay_days > 0 && <span className="delta delta-worse"> +{p.delay_days} hari</span>}
    {p.on_target_probability !== null && <small>Peluang tepat waktu {Math.round(p.on_target_probability * 100)}%</small>}
  </td>;
}

/** Semua anggota yang muncul di baseline atau skenario (skenario anggota baru menambah baris). */
function memberIds(columns: Evaluation[]): [string, string][] {
  const seen = new Map<string, string>();
  columns.forEach((c) => c.members.forEach((m) => seen.set(m.resource_id, m.resource_name)));
  return [...seen.entries()];
}
