/* Halaman Evaluasi: pilih skenario, jalankan perbandingan KPI terhadap baseline
   (UC-05 lihat KPI, UC-06 bandingkan skenario; layar "KPI and scenario comparison" Tabel 4.7).
   PEMILIK: Orang 1 — Frontend. */

import { useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { compareScenarios, getHistorical, getKpiDefinitions, MAX_COMPARED_SCENARIOS, type CompareResponse, type Historical, type KpiDefinition } from './api';
import { listScenarios, type Scenario } from '../simulasi/api';
import { SITUATION_ORDER, SITUATIONS } from '../simulasi/situations';
import { HistoricalPanel } from './HistoricalPanel';
import { KpiComparison } from './KpiComparison';
import { Button } from '../../shared/ui';
import './evaluasi.css';

const message = (error: unknown) => (error instanceof Error ? error.message : 'Terjadi kesalahan');

/** Skenario hanya bisa dibandingkan dengan skenario yang situasinya sama; ambil yang sejenis dengan pilihan pertama. */
function keepSameSituation(list: Scenario[], ids: string[]): string[] {
  const situationOf = (id: string) => list.find((s) => s.scenario_id === id)?.parameters.situation;
  const first = situationOf(ids[0]);
  return first ? ids.filter((id) => situationOf(id) === first) : [];
}

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

  const compare = async (ids: string[]) => {
    setBusy(true); setError(null);
    try { setResult(await compareScenarios({ scenario_ids: ids, replications, overload_threshold: threshold })); } catch (e) { setError(message(e)); } finally { setBusy(false); }
  };

  useEffect(() => {
    Promise.all([listScenarios(), getKpiDefinitions()])
      .then(([list, defs]) => {
        setScenarios(list); setDefinitions(defs);
        // ?scenarios=SCN-001,SCN-002 dari tombol "Bandingkan di Evaluasi"
        const requested = keepSameSituation(list, (params.get('scenarios') ?? '').split(',').filter((id) => list.some((s) => s.scenario_id === id)));
        const firstGroup = list.length ? list.filter((s) => s.parameters.situation === list[0].parameters.situation) : [];
        setChosen(requested.length ? requested : firstGroup.slice(0, MAX_COMPARED_SCENARIOS).map((s) => s.scenario_id));
        // Datang dari Simulasi: langsung tampilkan perbandingannya, tanpa klik tambahan.
        if (requested.length) void compare(requested);
      })
      .catch((e) => setError(message(e)));
  }, [params]);

  // Setelah hasil muncul, gulir ke hasil supaya tidak terlewat di bawah form.
  useEffect(() => {
    if (result) document.getElementById('hasil-perbandingan')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }, [result]);

  const toggle = (id: string) => setChosen((ids) => (ids.includes(id) ? ids.filter((x) => x !== id) : [...ids, id]));

  if (scenarios === null) return <section className="module-panel"><div className="empty-state"><p>{error ?? 'Memuat skenario…'}</p></div></section>;
  if (scenarios.length === 0) return <section className="module-panel"><div className="empty-state">
    <h3>Belum ada skenario</h3><p>Buat dan simpan skenario di halaman Simulasi sebelum membandingkan KPI.</p>
    <Link className="button" to="/simulasi">Buka Simulasi</Link>
  </div></section>;

  const tooMany = chosen.length > MAX_COMPARED_SCENARIOS;
  // Situasi yang "terkunci" oleh pilihan pertama; null jika belum ada pilihan.
  const lockedSituation = chosen.length ? scenarios.find((s) => s.scenario_id === chosen[0])?.parameters.situation ?? null : null;
  const sameKind = (situation: Scenario['parameters']['situation']) => lockedSituation === null || situation === lockedSituation;
  const selectAllSameKind = () => {
    const situation = lockedSituation ?? scenarios[0].parameters.situation;
    setChosen(scenarios.filter((s) => s.parameters.situation === situation).slice(0, MAX_COMPARED_SCENARIOS).map((s) => s.scenario_id));
  };
  return <div className="eval-page">
    <section className="module-panel" aria-label="Pilihan perbandingan">
      <div className="panel-heading"><h2>Bandingkan skenario dengan baseline</h2><span className="subtle-badge">{chosen.length} dari maks. {MAX_COMPARED_SCENARIOS} dipilih</span></div>
      <form className="eval-controls" onSubmit={(e) => { e.preventDefault(); void compare(chosen); }}>
        <fieldset className="check-list">
          <legend className="eyebrow">Skenario</legend>
          {lockedSituation
            ? <p className="text-caption">Membandingkan skenario <strong>{SITUATIONS[lockedSituation].label}</strong>. Skenario dengan situasi lain dinonaktifkan; kosongkan pilihan untuk mengganti.</p>
            : <p className="text-caption">Skenario hanya bisa dibandingkan dengan skenario yang situasinya sama.</p>}
          {SITUATION_ORDER.map((situation) => {
            const group = scenarios.filter((s) => s.parameters.situation === situation);
            if (group.length === 0) return null;
            return <div key={situation} className="eval-group">
              <p className="eyebrow">{SITUATIONS[situation].label}</p>
              {group.map((s) => <label key={s.scenario_id} className={`field-check ${sameKind(situation) ? '' : 'is-disabled'}`}>
                <input type="checkbox" checked={chosen.includes(s.scenario_id)} disabled={!sameKind(situation)} onChange={() => toggle(s.scenario_id)} />
                <span>{s.name}<small>{s.scenario_id}</small></span>
              </label>)}
            </div>;
          })}
          <div className="eval-selection-actions">
            <Button variant="ghost" size="sm" onClick={selectAllSameKind}>Pilih semua sejenis</Button>
            <Button variant="ghost" size="sm" disabled={chosen.length === 0} onClick={() => setChosen([])}>Kosongkan</Button>
          </div>
        </fieldset>
        <div className="eval-settings">
          <label className="field eval-replications"><span>Replikasi Monte Carlo</span>
            <input type="number" min={0} max={1000} step={50} value={replications} onChange={(e) => setReplications(Number(e.target.value))} />
            <small>0 = hanya estimasi tunggal. 100 replikasi (bawaan FR-04.2) menampilkan median, rentang P10–P90, dan peluang tepat waktu (lebih lama).</small>
          </label>
          <label className="field eval-replications"><span>Threshold overload RLI</span>
            <input type="number" min={0.1} max={10} step={0.1} value={threshold} onChange={(e) => setThreshold(Number(e.target.value))} />
            <small>RLI di atas nilai ini dihitung overload (FR-04.4). Bawaan 1,0.</small>
          </label>
        </div>
        <div className="eval-submit">
          {chosen.length === 0 && <p className="notice notice-warning">Pilih minimal satu skenario untuk dibandingkan.</p>}
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