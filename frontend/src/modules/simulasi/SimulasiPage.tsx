/* Halaman Simulasi: daftar skenario, form scenario setup, dan hasil simulasi.
   Alur: buat/pilih skenario → simpan → jalankan → lihat hasil (UC-01 s.d. UC-04).
   PEMILIK: Orang 1 — Frontend. */

import { useEffect, useRef, useState } from 'react';
import {
  createScenario, deleteScenario, duplicateScenario, getBaseline, listScenarios, runScenario, updateScenario,
  type Baseline, type Scenario, type ScenarioInput, type ScenarioParameters, type SimulationRun,
} from './api';
import { compareScenarios, getKpiDefinitions, type Evaluation, type KpiDefinition } from '../evaluasi/api';
import { ScenarioForm, type Draft } from './ScenarioForm';
import { SimulationResultView } from './SimulationResultView';
import { SITUATIONS } from './situations';
import { formatDate } from '../../shared/format';
import { Button, ConfirmDialog, Toast, type AlertVariant } from '../../shared/ui';
import './simulasi.css';

const NEW = 'new';

type Notice = { variant: AlertVariant; title: string; message?: string };

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
  const [notice, setNotice] = useState<Notice | null>(null);
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const resultRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    Promise.all([getBaseline(), listScenarios(), getKpiDefinitions()])
      .then(([b, list, defs]) => {
        setBaseline(b); setScenarios(list); setDefinitions(defs);
        if (list.length) { setSelected(list[0].scenario_id); setDraft(toDraft(list[0])); } else setDraft(newDraft(b));
      })
      .catch((e) => setLoadError(message(e)));
  }, []);

  // Setelah simulasi selesai, bawa pengguna langsung ke hasilnya.
  useEffect(() => {
    if (run) resultRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }, [run]);

  if (loadError) return <section className="module-panel"><div className="empty-state"><h3>Baseline belum bisa dimuat</h3><p>{loadError}. Pastikan backend berjalan, lalu muat ulang halaman.</p></div></section>;
  if (!baseline || !draft) return <section className="module-panel"><div className="empty-state"><p>Memuat baseline…</p></div></section>;

  const select = (id: string) => {
    setSelected(id); setRun(null); setKpis(null); setError(null);
    const found = scenarios.find((s) => s.scenario_id === id);
    setDraft(found ? toDraft(found) : newDraft(baseline));
  };

  /* Jalankan aksi async dengan status sibuk, pesan error, dan toast sukses yang seragam. */
  const act = async (label: string, action: () => Promise<void>, success?: string) => {
    setBusy(label); setError(null);
    try {
      await action();
      if (success) setNotice({ variant: 'success', title: success });
    } catch (e) { setError(message(e)); } finally { setBusy(null); }
  };

  /* Simpan draft (buat baru atau update) dan kembalikan skenario tersimpan. */
  const persist = async (): Promise<Scenario> => {
    const saved = selected === NEW ? await createScenario(toInput(draft)) : await updateScenario(selected, toInput(draft));
    setScenarios((list) => [...list.filter((s) => s.scenario_id !== saved.scenario_id), saved].sort((a, b) => a.created_at.localeCompare(b.created_at)));
    setSelected(saved.scenario_id);
    setDraft(toDraft(saved));
    return saved;
  };

  const save = () => act('save', async () => { await persist(); }, 'Skenario tersimpan');

  const duplicate = () => act('duplicate', async () => {
    const copy = await duplicateScenario(selected);
    setScenarios((list) => [...list, copy]);
    setSelected(copy.scenario_id); setDraft(toDraft(copy)); setRun(null); setKpis(null);
  }, 'Skenario diduplikat');

  const remove = () => act('delete', async () => {
    await deleteScenario(selected);
    const rest = scenarios.filter((s) => s.scenario_id !== selected);
    setScenarios(rest);
    setRun(null); setKpis(null);
    if (rest.length) { setSelected(rest[0].scenario_id); setDraft(toDraft(rest[0])); }
    else { setSelected(NEW); setDraft(newDraft(baseline)); }
  }, 'Skenario dihapus');

  /* UC-03: simulasi hanya untuk skenario tersimpan, jadi draft disimpan dulu. */
  const simulate = () => act('run', async () => {
    const saved = await persist();
    const [result, comparison] = await Promise.all([
      runScenario(saved.scenario_id),
      compareScenarios({ scenario_ids: [saved.scenario_id], replications: 0 }),
    ]);
    setRun(result); setKpis(comparison.scenarios[0] ?? null);
  }, 'Simulasi selesai');

  const saved = selected !== NEW;
  return <div className="sim-page">
    <div className="sim-context">
      <span className="badge badge-accent">Sumber data: {baseline.data_source === 'synthetic' ? 'sintetis' : 'PuTI'}</span>
      <span className="badge" title={baseline.notes.join('\n')}>{baseline.as_of && <>Data per {formatDate(baseline.as_of)} · </>}Baseline mulai {formatDate(baseline.start_date)}</span>
      <span className="badge">{baseline.projects.length} proyek · {baseline.resources.length} anggota · {baseline.tasks.length} task</span>
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
          {saved && <span className="sim-scenario-id">{selected}</span>}
        </div>

        <form className="sim-editor" onSubmit={(e) => { e.preventDefault(); void simulate(); }}>
          <ScenarioForm baseline={baseline} draft={draft} onChange={setDraft} />
          {error && <p className="notice notice-danger" role="alert">{error}</p>}

          <div className="sim-actions">
            <div className="sim-actions-secondary">
              <Button variant="outline" disabled={!saved || busy !== null} onClick={() => void duplicate()}>Duplikat</Button>
              <Button variant="outline" disabled={!saved || busy !== null} onClick={() => setConfirmingDelete(true)}>Hapus</Button>
            </div>
            <div className="sim-actions-primary">
              <Button variant="outline" loading={busy === 'save'} disabled={busy !== null} onClick={() => void save()}>
                {busy === 'save' ? 'Menyimpan…' : 'Simpan'}
              </Button>
              <Button type="submit" variant="primary" loading={busy === 'run'} disabled={busy !== null}>
                {busy === 'run' ? 'Menjalankan…' : 'Simpan & jalankan simulasi'}
              </Button>
            </div>
          </div>
        </form>
      </section>
    </div>

    {run && <section ref={resultRef} className="module-panel" aria-label="Hasil simulasi">
      <div className="panel-heading"><h2>Hasil simulasi: {run.scenario.name}</h2><span className="subtle-badge">Data {run.data_source === 'synthetic' ? 'sintetis' : 'PuTI'}</span></div>
      <SimulationResultView run={run} kpis={kpis} definitions={definitions} />
    </section>}

    <ConfirmDialog
      open={confirmingDelete}
      onClose={() => setConfirmingDelete(false)}
      onConfirm={() => { void remove().then(() => setConfirmingDelete(false)); }}
      title="Hapus skenario?"
      description={`Skenario "${draft.name}" akan dihapus permanen dan tidak bisa dikembalikan.`}
      confirmLabel="Hapus"
      cancelLabel="Batal"
      destructive
      loading={busy === 'delete'}
    />
    <Toast open={notice !== null} variant={notice?.variant} title={notice?.title ?? ''} message={notice?.message} onClose={() => setNotice(null)} />
  </div>;
}