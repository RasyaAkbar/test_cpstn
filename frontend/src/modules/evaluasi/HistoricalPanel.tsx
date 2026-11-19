import type { GroupRatio, Historical } from './api';
import { formatDate, formatNumber } from '../../shared/format';
import './historical.css';

export function HistoricalPanel({ data }: { data: Historical }) {
  return <section className="module-panel" aria-label="KPI historis">
    <div className="panel-heading">
      <h2>Kalibrasi dari data aktual</h2>
      <span className="subtle-badge">Data per {formatDate(data.as_of)}</span>
    </div>
    <div className="hist-grid">
      <RatioBlock title="Estimate Accuracy Ratio" code="FR-04.8" overall={data.ear} unit="" groups={[['Kompleksitas', data.ear_by_complexity], ['Role', data.ear_by_role]]}
        note="Durasi aktual / estimasi pada task selesai. 1,0 = tepat; di atas 1 = estimasi terlalu optimis." />
      <RatioBlock title="Rework Rate" code="FR-04.9" overall={data.rework_rate} unit="%" groups={[['Role', data.rework_by_role], ['Proyek', data.rework_by_project]]}
        note="Task yang pernah ditolak QA / task yang masuk fase QA." />
    </div>
    {data.notes.length > 0 && <details className="hist-notes">
      <summary>Cara data disiapkan untuk simulasi ({data.notes.length} catatan)</summary>
      <ul>{data.notes.map((n) => <li key={n}>{n}</li>)}</ul>
    </details>}
  </section>;
}

type BlockProps = { title: string; code: string; overall: number | null; unit: string; groups: [string, GroupRatio[]][]; note: string };

function RatioBlock({ title, code, overall, unit, groups, note }: BlockProps) {
  return <div className="hist-block">
    <header className="hist-head">
      <div><h3>{title}</h3><span className="hist-code">{code}</span></div>
      <strong className="hist-value">{formatNumber(overall)}{overall !== null && unit}</strong>
    </header>
    <p className="hist-note">{note}</p>
    {groups.map(([label, rows]) => rows.length > 0 && <div key={label} className="hist-table-wrap">
      <table className="data-table hist-table">
        <thead><tr><th>{label}</th><th className="num">Nilai</th><th className="num">Task</th></tr></thead>
        <tbody>{rows.map((g) => <tr key={g.key}><td title={g.label}>{g.label}</td><td className="num">{formatNumber(g.value)}{g.value !== null && unit}</td><td className="num">{g.tasks}</td></tr>)}</tbody>
      </table>
    </div>)}
  </div>;
}