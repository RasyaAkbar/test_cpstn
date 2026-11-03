/* Halaman Simulasi: daftar skenario, form scenario setup, dan hasil simulasi.
   Alur: buat/pilih skenario → simpan → jalankan → lihat hasil (UC-01 s.d. UC-04).
   PEMILIK: Orang 1 — Frontend. */

import { useEffect, useState } from 'react';
import {
  createScenario, deleteScenario, duplicateScenario, getBaseline, listScenarios, runScenario, updateScenario,
  type Baseline, type Scenario, type ScenarioInput, type ScenarioParameters, type SimulationRun,
} from './api';
import { compareScenarios, getKpiDefinitions, type Evaluation, type KpiDefinition } from '../evaluasi/api';
import { ScenarioForm, type Draft } from './ScenarioForm';
import { SimulationResultView } from './SimulationResultView';
import { SITUATIONS } from './situations';
import { formatDate } from '../../shared/format';
import './simulasi.css';

const NEW = 'new';

function newDraft(baseline: Baseline): Draft {
  return { name: 'Skenario baru', description: '', parameters: { situation: 'member_absence', ...SITUATIONS.member_absence.defaults(baseline) } };
}

const toDraft = (s: Scenario): Draft => ({ name: s.name, description: s.description, parameters: { ...s.parameters } });
const toInput = (d: Draft): ScenarioInput => ({ name: d.name.trim(), description: d.description, parameters: d.parameters as unknown as ScenarioParameters });
const message = (error: unknown) => (error instanceof Error ? error.message : 'Terjadi kesalahan');

export function SimulasiPage() {
  const [baseline, setBaseline] = useState<Baseline | null>(null);
  const [definitions, setDefinitions] = useState<KpiDefinition[]>([]);
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [selected, setSelected] = useState<string>(NEW); // scenario_id atau NEW
  const [draft, setDraft] = useState<Draft | null>(null);
  const [run, setRun] = useState<SimulationRun | null>(null);
  const [kpis, setKpis] = useState<Evaluation | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([getBaseline(), listScenarios(), getKpiDefinitions()])
      .then(([b, list, defs]) => {
        setBaseline(b); setScenarios(list); setDefinitions(defs);
        if (list.length) { setSelected(list[0].scenario_id); setDraft(toDraft(list[0])); } else setDraft(newDraft(b));
      })
      .catch((e) => setLoadError(message(e)));
  }, []);

  if (loadError) return <section className="module-panel"><div className="empty-state"><h3>Baseline belum bisa dimuat</h3><p>{loadError}. Pastikan backend berjalan, lalu muat ulang halaman.</p></div></section>;
  if (!baseline || !draft) return <section className="module-panel"><div className="empty-state"><p>Memuat baseline…</p></div></section>;

  const select = (id: string) => {
    setSelected(id); setRun(null); setKpis(null); setError(null);
    const found = scenarios.find((s) => s.scenario_id === id);
    setDraft(found ? toDraft(found) : newDraft(baseline));
  };

  /* Jalankan aksi async dengan status sibuk dan pesan error yang seragam. */
  const act = async (label: string, action: () => Promise<void>) => {
    setBusy(label); setError(null);
    try { await action(); } catch (e) { setError(message(e)); } finally { setBusy(null); }
  };

  /* Simpan draft (buat baru atau update) dan kembalikan skenario tersimpan. */
  const persist = async (): Promise<Scenario> => {
    const saved = selected === NEW ? await createScenario(toInput(draft)) : await updateScenario(selected, toInput(draft));
    setScenarios((list) => [...list.filter((s) => s.scenario_id !== saved.scenario_id), saved].sort((a, b) => a.created_at.localeCompare(b.created_at)));
    setSelected(saved.scenario_id);
    setDraft(toDraft(saved));
    return saved;
  };

  const save = () => act('save', async () => { await persist(); });

  const duplicate = () => act('duplicate', async () => {
    const copy = await duplicateScenario(selected);
    setScenarios((list) => [...list, copy]);
    setSelected(copy.scenario_id); setDraft(toDraft(copy)); setRun(null); setKpis(null);
  });

  const remove = () => act('delete', async () => {
    await deleteScenario(selected);
    const rest = scenarios.filter((s) => s.scenario_id !== selected);
    setScenarios(rest); setRun(null); setKpis(null);
    if (rest.length) { setSelected(rest[0].scenario_id); setDraft(toDraft(rest[0])); } else { setSelected(NEW); setDraft(newDraft(baseline)); }
  });

  /* UC-03: simulasi hanya untuk skenario tersimpan, jadi draft disimpan dulu. */
  const simulate = () => act('run', async () => {
    const saved = await persist();
    const [result, comparison] = await Promise.all([
      runScenario(saved.scenario_id),
      compareScenarios({ scenario_ids: [saved.scenario_id], replications: 0 }),
    ]);
    setRun(result); setKpis(comparison.scenarios[0] ?? null);
  });

  const saved = selected !== NEW;
  return <div className="sim-page">
    <div className="sim-context">
      <span className="badge badge-accent">Sumber data: {baseline.data_source === 'synthetic' ? 'sintetis' : 'PuTI'}</span>
      <span className="badge">Baseline mulai {formatDate(baseline.start_date)}</span>
      <span className="badge">{baseline.projects.length} proyek · {baseline.resources.length} anggota · {baseline.tasks.length} task</span>
    </div>

    <div className="sim-layout">
      <aside className="module-panel sim-list" aria-label="Skenario tersimpan">
        <div className="panel-heading"><h2>Skenario</h2><button type="button" className="button button-ghost" onClick={() => select(NEW)}>+ Baru</button></div>
        <ul>
          {selected === NEW && <li><button type="button" className="sim-list-item active">Skenario baru (belum disimpan)</button></li>}
          {scenarios.map((s) => <li key={s.scenario_id}>
            <button type="button" className={`sim-list-item ${s.scenario_id === selected ? 'active' : ''}`} onClick={() => select(s.scenario_id)}>
              <strong>{s.name}</strong><small>{SITUATIONS[s.parameters.situation].label} · {s.scenario_id}</small>
            </button>
          </li>)}
          {scenarios.length === 0 && selected !== NEW && <li className="text-caption">Belum ada skenario.</li>}
        </ul>
      </aside>

      <section className="module-panel" aria-label="Scenario setup">
        <div className="panel-heading"><h2>{saved ? draft.name : 'Skenario baru'}</h2>{saved && <span className="subtle-badge">{selected}</span>}</div>
        <form className="sim-editor" onSubmit={(e) => { e.preventDefault(); void simulate(); }}>
          <ScenarioForm baseline={baseline} draft={draft} onChange={setDraft} />
          {error && <p className="notice notice-danger" role="alert">{error}</p>}
          <div className="sim-actions">
            <button type="submit" className="button" disabled={busy !== null}>{busy === 'run' ? 'Menjalankan…' : 'Simpan & jalankan simulasi'}</button>
            <button type="button" className="button button-ghost" disabled={busy !== null} onClick={() => void save()}>{busy === 'save' ? 'Menyimpan…' : 'Simpan'}</button>
            <button type="button" className="button button-ghost" disabled={!saved || busy !== null} onClick={() => void duplicate()}>Duplikat</button>
            <button type="button" className="button button-ghost button-danger" disabled={!saved || busy !== null} onClick={() => void remove()}>Hapus</button>
          </div>
        </form>
      </section>
    </div>

    {run && <section className="module-panel" aria-label="Hasil simulasi">
      <div className="panel-heading"><h2>Hasil simulasi: {run.scenario.name}</h2><span className="subtle-badge">Data {run.data_source === 'synthetic' ? 'sintetis' : 'PuTI'}</span></div>
      <SimulationResultView run={run} kpis={kpis} definitions={definitions} />
    </section>}
  </div>;
}
