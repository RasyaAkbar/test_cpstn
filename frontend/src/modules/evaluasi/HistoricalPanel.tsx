/* KPI dari data aktual yang tidak bergantung pada skenario: Estimate Accuracy Ratio
   (FR-04.8) dan Rework Rate (FR-04.9), plus catatan cara data disiapkan untuk simulasi.
   PEMILIK: Orang 1 — Frontend. Angka dihitung backend (evaluasi/historical.py). */

import type { GroupRatio, Historical } from './api';
import { formatDate, formatNumber } from '../../shared/format';

export function HistoricalPanel({ data }: { data: Historical }) {
  return <section className="module-panel" aria-label="KPI historis">
    <div className="panel-heading">
      <h2>Kalibrasi dari data aktual</h2>
      <span className="subtle-badge">Data per {formatDate(data.as_of)}</span>
    </div>
    <div className="eval-history">
      <RatioTable title="Estimate Accuracy Ratio (FR-04.8)" overall={data.ear} unit="" groups={[['Kompleksitas', data.ear_by_complexity], ['Role', data.ear_by_role]]}
        note="Durasi aktual / estimasi pada task selesai. 1,0 = tepat; di atas 1 = estimasi terlalu optimis." />
      <RatioTable title="Rework Rate (FR-04.9)" overall={data.rework_rate} unit="%" groups={[['Role', data.rework_by_role], ['Proyek', data.rework_by_project]]}
        note="Task yang pernah ditolak QA / task yang masuk fase QA." />
    </div>
    {data.notes.length > 0 && <details className="eval-notes">
      <summary>Cara data disiapkan untuk simulasi ({data.notes.length} catatan)</summary>
      <ul>{data.notes.map((n) => <li key={n}>{n}</li>)}</ul>
    </details>}
  </section>;
}

function RatioTable({ title, overall, unit, groups, note }: { title: string; overall: number | null; unit: string; groups: [string, GroupRatio[]][]; note: string }) {
  return <div className="eval-history-block">
    <h3>{title}: <strong>{formatNumber(overall)}{overall !== null && unit}</strong></h3>
    <p className="text-caption">{note}</p>
    {groups.map(([label, rows]) => rows.length > 0 && <div key={label} className="table-scroll"><table className="data-table">
      <thead><tr><th>{label}</th><th className="num">Nilai</th><th className="num">Task</th></tr></thead>
      <tbody>{rows.map((g) => <tr key={g.key}><td>{g.label}</td><td className="num">{formatNumber(g.value)}{g.value !== null && unit}</td><td className="num">{g.tasks}</td></tr>)}</tbody>
    </table></div>)}
  </div>;
}
