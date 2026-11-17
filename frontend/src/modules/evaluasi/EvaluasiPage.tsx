/* Halaman Evaluasi: pilih skenario, jalankan perbandingan KPI terhadap baseline
   (UC-05 lihat KPI, UC-06 bandingkan skenario; layar "KPI and scenario comparison" Tabel 4.7).
   PEMILIK: Orang 1 — Frontend. */

import { useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { compareScenarios, getHistorical, getKpiDefinitions, MAX_COMPARED_SCENARIOS, type CompareResponse, type Historical, type KpiDefinition } from './api';
import { listScenarios, type Scenario } from '../simulasi/api';
import { SITUATIONS } from '../simulasi/situations';
import { HistoricalPanel } from './HistoricalPanel';
import { KpiComparison } from './KpiComparison';
import { Button } from '../../shared/ui';
import './evaluasi.css';

const message = (error: unknown) => (error instanceof Error ? error.message : 'Terjadi kesalahan');

export function EvaluasiPage() {
  const [params] = useSearchParams();
  const [scenarios, setScenarios] = useState<Scenario[] | null>(null);
  const [definitions, setDefinitions] = useState<KpiDefinition[]>([]);
  const [chosen, setChosen] = useState<string[]>([]);
  const [replications, setReplications] = useState(100);
  const [threshold, setThreshold] = useState(1);
  const [result, setResult] = useState<CompareResponse | null>(null);
  const [historical, setHistorical] = useState<Historical | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // KPI historis tidak bergantung pada skenario; gagal memuatnya tidak menghalangi perbandingan.
  useEffect(() => { getHistorical().then(setHistorical).catch(() => setHistorical(null)); }, []);

  useEffect(() => {
    Promise.all([listScenarios(), getKpiDefinitions()])
      .then(([list, defs]) => {
        setScenarios(list); setDefinitions(defs);
        // ?scenarios=SCN-001,SCN-002 dari tombol "Bandingkan di Evaluasi"
        const requested = (params.get('scenarios') ?? '').split(',').filter((id) => list.some((s) => s.scenario_id === id));
        setChosen(requested.length ? requested : list.slice(0, MAX_COMPARED_SCENARIOS).map((s) => s.scenario_id));
      })
      .catch((e) => setError(message(e)));
  }, [params]);

  const toggle = (id: string) => setChosen((ids) => (ids.includes(id) ? ids.filter((x) => x !== id) : [...ids, id]));

  const runComparison = async () => {
    setBusy(true); setError(null);
    try { setResult(await compareScenarios({ scenario_ids: chosen, replications, overload_threshold: threshold })); } catch (e) { setError(message(e)); } finally { setBusy(false); }
  };

  if (scenarios === null) return <section className="module-panel"><div className="empty-state"><p>{error ?? 'Memuat skenario…'}</p></div></section>;
  if (scenarios.length === 0) return <section className="module-panel"><div className="empty-state">
    <h3>Belum ada skenario</h3><p>Buat dan simpan skenario di halaman Simulasi sebelum membandingkan KPI.</p>
    <Link className="button" to="/simulasi">Buka Simulasi</Link>
  </div></section>;

  const tooMany = chosen.length > MAX_COMPARED_SCENARIOS;
  return <div className="eval-page">
    <section className="module-panel" aria-label="Pilihan perbandingan">
      <div className="panel-heading"><h2>Bandingkan skenario dengan baseline</h2><span className="subtle-badge">Maks. {MAX_COMPARED_SCENARIOS} skenario</span></div>
      <form className="eval-controls" onSubmit={(e) => { e.preventDefault(); void runComparison(); }}>
        <fieldset className="check-list">
          <legend className="eyebrow">Skenario</legend>
          {scenarios.map((s) => <label key={s.scenario_id} className="field-check">
            <input type="checkbox" checked={chosen.includes(s.scenario_id)} onChange={() => toggle(s.scenario_id)} />
            <span>{s.name}<small>{SITUATIONS[s.parameters.situation].label} · {s.scenario_id}</small></span>
          </label>)}
        </fieldset>
        <label className="field eval-replications"><span>Replikasi Monte Carlo</span>
          <input type="number" min={0} max={1000} step={50} value={replications} onChange={(e) => setReplications(Number(e.target.value))} />
          <small>0 = hanya estimasi tunggal. 100 replikasi (bawaan FR-04.2) menampilkan median, rentang P10–P90, dan peluang tepat waktu (lebih lama).</small>
        </label>
        <label className="field eval-replications"><span>Threshold overload RLI</span>
          <input type="number" min={0.1} max={10} step={0.1} value={threshold} onChange={(e) => setThreshold(Number(e.target.value))} />
          <small>RLI di atas nilai ini dihitung overload (FR-04.4). Bawaan 1,0.</small>
        </label>
        <div className="eval-submit">
          {tooMany && <p className="notice notice-warning">Pilih maksimal {MAX_COMPARED_SCENARIOS} skenario.</p>}
          {error && <p className="notice notice-danger" role="alert">{error}</p>}
          <Button
            type="submit"
            variant="primary"
            loading={busy}
            disabled={busy || chosen.length === 0 || tooMany}
          >
            {busy ? 'Menghitung…' : 'Bandingkan KPI'}
          </Button>
        </div>
      </form>
    </section>
    {result && <KpiComparison result={result} definitions={definitions} />}
    {historical && <HistoricalPanel data={historical} />}
  </div>;
}
