/* Tabel perbandingan KPI baseline vs skenario, penanda nilai lebih buruk, indikator
   peringkat skenario, ketepatan target per proyek, dan beban per anggota (FR-06, Tabel 4.7).
   PEMILIK: Orang 1 — Frontend. Definisi dan arah KPI datang dari backend (Orang 3). */

import type { CompareResponse, Evaluation, KpiDefinition, KpiValue } from './api';
import { formatDate, formatNumber, formatSigned } from '../../shared/format';

type Props = { result: CompareResponse; definitions: KpiDefinition[] };

const STATUS_LABEL = { better: 'lebih baik', worse: 'lebih buruk', same: 'sama' } as const;

export function KpiComparison({ result, definitions }: Props) {
  const columns = [result.baseline, ...result.scenarios];
  const best = result.scenarios.find((s) => s.scenario_id === result.best_scenario_id);
  const withRange = result.replications > 0;
  const worseKpis = best ? best.kpis.filter((kpi) => kpi.status === 'worse') : [];
  const hasWorseKpis = worseKpis.length > 0;

  return (
    <>
      <section className="module-panel" aria-label="Perbandingan KPI">
        <div className="panel-heading">
          <h2>Perbandingan KPI</h2>
          <span className="subtle-badge">
            Data {result.data_source === 'synthetic' ? 'sintetis' : 'PuTI'} ·{' '}
            {withRange ? `${result.replications} replikasi` : 'estimasi tunggal'}
          </span>
        </div>

        {best && (
          <div className="eval-best">
            <div className="eval-best-heading">
              <span className="eval-best-indicator" aria-hidden="true" />
              <strong>Skenario dengan peringkat tertinggi: {best.name}</strong>
            </div>
            <p>
              Skenario ini memiliki peringkat tertinggi di antara skenario yang dibandingkan,
              berdasarkan urutan prioritas KPI: {result.ranking_basis.join(' → ')}.
            </p>
            <p className="eval-best-note">
              Peringkat tertinggi tidak selalu berarti hasilnya lebih baik daripada baseline.
              Perhatikan perubahan setiap KPI sebelum menentukan keputusan. Keputusan akhir
              tetap berada pada Kepala Seksi dan System Analyst.
            </p>
            {hasWorseKpis && (
              <p className="eval-ranking-warning">
                {worseKpis.length} KPI pada skenario ini menunjukkan hasil yang lebih buruk
                dibanding baseline.
              </p>
            )}
          </div>
        )}

        <div className="table-scroll">
          <table className="data-table kpi-table">
            <thead>
              <tr>
                <th>KPI</th>
                {columns.map((c) => (
                  <th
                    key={c.scenario_id ?? 'baseline'}
                    className={c.scenario_id != null && c.scenario_id === result.best_scenario_id ? 'is-best' : ''}
                  >
                    <span className="eval-column-name">{c.name}</span>
                    {c.scenario_id != null && c.scenario_id === result.best_scenario_id && (
                      <span className="eval-column-best">Peringkat #1</span>
                    )}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {definitions.map((def) => (
                <tr key={def.key}>
                  <th scope="row" title={def.description}>
                    {def.label}
                    <small>
                      {def.unit} · {def.better === 'lower' ? 'makin kecil makin baik' : 'makin besar makin baik'}
                    </small>
                  </th>
                  {columns.map((c) => (
                    <KpiCell
                      key={c.scenario_id ?? 'baseline'}
                      value={c.kpis.find((k) => k.key === def.key)}
                      best={c.scenario_id != null && c.scenario_id === result.best_scenario_id}
                    />
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="text-caption eval-footnote">
          Nilai utama memakai estimasi effort dari data.{' '}
          {withRange && 'Baris kecil menampilkan median dan rentang P10–P90 dari replikasi, karena hasil simulasi bersifat acak. '}
          Delta = skenario − baseline.
        </p>
      </section>

      <section className="module-panel" aria-label="Target launch per proyek">
        <div className="panel-heading"><h2>Target launch per proyek</h2></div>
        <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th>Proyek</th>
                <th>Target</th>
                {columns.map((c) => <th key={c.scenario_id ?? 'baseline'}>{c.name}</th>)}
              </tr>
            </thead>
            <tbody>
              {result.baseline.projects.map((p) => (
                <tr key={p.project_id}>
                  <td>{p.project_name}</td>
                  <td>{formatDate(p.target_launch_date)}</td>
                  {columns.map((c) => (
                    <ProjectCell key={c.scenario_id ?? 'baseline'} evaluation={c} projectId={p.project_id} />
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="module-panel" aria-label="Beban per anggota">
        <div className="panel-heading"><h2>Beban anggota terhadap kapasitas</h2></div>
        <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th>Anggota</th>
                {columns.map((c) => <th key={c.scenario_id ?? 'baseline'} className="num">{c.name}</th>)}
              </tr>
            </thead>
            <tbody>
              {memberIds(columns).map(([id, name]) => (
                <tr key={id}>
                  <td>{name}</td>
                  {columns.map((c) => {
                    const m = c.members.find((x) => x.resource_id === id);
                    return (
                      <td
                        key={c.scenario_id ?? 'baseline'}
                        className={`num ${m?.overloaded ? 'cell-danger' : ''}`}
                        title={m ? `${formatNumber(m.demand_days)} / ${formatNumber(m.capacity_days)} hari-orang` : undefined}
                      >
                        {m ? (
                          <div className="eval-workload-cell">
                            <div className="eval-workload-value">
                              <strong>{formatNumber(m.load_pct)}%</strong>
                              {m.overloaded && <span className="eval-overload-label">Overload</span>}
                            </div>
                            <div
                              className="eval-workload-track"
                              role="progressbar"
                              aria-label={`Beban ${m.resource_name}`}
                              aria-valuemin={0}
                              aria-valuemax={100}
                              aria-valuenow={Math.max(0, Math.min(100, m.load_pct))}
                              aria-valuetext={`${formatNumber(m.load_pct)}%`}
                            >
                              <span
                                className={`eval-workload-fill ${m.overloaded ? 'is-overloaded' : ''}`}
                                style={{ width: `${Math.max(0, Math.min(100, m.load_pct))}%` }}
                              />
                            </div>
                          </div>
                        ) : '—'}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="text-caption eval-footnote">
          Beban = pekerjaan anggota / kapasitasnya sampai target proyek terakhir yang ia kerjakan.
          Di atas 100% = overload.
        </p>
      </section>
    </>
  );
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
  return (
    <td className={p.on_target ? '' : 'cell-danger'}>
      <div className="eval-project-cell">
        <strong>{formatDate(p.projected_finish)}</strong>
        <span className={p.on_target ? 'eval-project-status is-on-target' : 'eval-project-status is-delayed'}>
          {p.on_target ? 'Tepat waktu' : `Terlambat ${formatNumber(p.delay_days)} hari`}
        </span>
        {p.on_target_probability !== null && (
          <small>Peluang tepat waktu: {Math.round(p.on_target_probability * 100)}%</small>
        )}
      </div>
    </td>
  );
}

/** Semua anggota yang muncul di baseline atau skenario (skenario anggota baru menambah baris). */
function memberIds(columns: Evaluation[]): [string, string][] {
  const seen = new Map<string, string>();
  columns.forEach((c) => c.members.forEach((m) => seen.set(m.resource_id, m.resource_name)));
  return [...seen.entries()];
}
