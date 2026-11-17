import { Button } from '../../shared/ui';
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


  const remove = () => {
    if (selected === NEW) return;

    const confirmed = window.confirm(
      `Hapus skenario "${draft.name}"?\n\nTindakan ini tidak dapat dibatalkan.`
    );

    if (!confirmed) return;

    void act('delete', async () => {
      await deleteScenario(selected);

      const rest = scenarios.filter(
        (s) => s.scenario_id !== selected
      );

      setScenarios(rest);
      setRun(null);
      setKpis(null);

      if (rest.length) {
        setSelected(rest[0].scenario_id);
        setDraft(toDraft(rest[0]));
      } else {
        setSelected(NEW);
        setDraft(newDraft(baseline));
      }
    });
  };


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

    <div className="sim-context" aria-label="Informasi baseline">
      <span className="sim-data-source">
        <span className="sim-status-dot" aria-hidden="true" />
        {baseline.data_source === 'synthetic'
          ? 'Data sintetis'
          : 'Data PuTI'}
      </span>

      <span className="sim-context-divider" aria-hidden="true" />

      <span>Baseline: {formatDate(baseline.start_date)}</span>

      <span className="sim-context-divider" aria-hidden="true" />

      <span>
        {baseline.projects.length} proyek
        <span className="sim-meta-separator">·</span>
        {baseline.resources.length} anggota
        <span className="sim-meta-separator">·</span>
        {baseline.tasks.length} task
      </span>
    </div>


    <div className="sim-layout">
      <aside className="module-panel sim-list" aria-label="Skenario tersimpan">
        <div className="panel-heading"><h2>Skenario</h2><Button variant="outline" size="sm" onClick={() => select(NEW)}>+ Baru</Button></div>
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

        <div className="panel-heading sim-editor-heading">
          <div className="sim-editor-heading-content">
            <h2>{draft.name.trim() || 'Skenario tanpa nama'}</h2>
            <p className="sim-editor-subtitle">
              {SITUATIONS[draft.parameters.situation].label}
              {!saved && ' · Belum disimpan'}
            </p>
          </div>

          {saved && (
            <span className="sim-scenario-id">
              {selected}
            </span>
          )}
        </div>

        <form className="sim-editor" onSubmit={(e) => { e.preventDefault(); void simulate(); }}>
          <ScenarioForm baseline={baseline} draft={draft} onChange={setDraft} />
          {error && <p className="notice notice-danger" role="alert">{error}</p>}

          <div className="sim-actions">
            <div className="sim-actions-secondary">
              <Button
                variant="outline"
                disabled={!saved || busy !== null}
                onClick={() => void duplicate()}
              >
                Duplikat
              </Button>
              <Button
                variant="outline"
                disabled={!saved || busy !== null}
                onClick={() => void remove()}
              >
                Hapus
              </Button>
            </div>

            <div className="sim-actions-primary">
              <Button
                variant="outline"
                loading={busy === 'save'}
                disabled={busy !== null}
                onClick={() => void save()}
              >
                {busy === 'save' ? 'Menyimpan…' : 'Simpan'}
              </Button>
              <Button
                type="submit"
                variant="primary"
                loading={busy === 'run'}
                disabled={busy !== null}
              >
                {busy === 'run'
                  ? 'Menjalankan…'
                  : 'Simpan & jalankan simulasi'}
              </Button>
            </div>
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
