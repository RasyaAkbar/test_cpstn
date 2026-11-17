/* Format tampilan bersama halaman Simulasi dan Evaluasi.
   PEMILIK: Orang 1 — Frontend. */

const dateFormat = new Intl.DateTimeFormat('id-ID', { day: 'numeric', month: 'short', year: 'numeric' });
// 2 desimal: indeks KPI seperti RLI dan WBI bernilai sekitar 0–3.
const numberFormat = new Intl.NumberFormat('id-ID', { maximumFractionDigits: 2 });

/** "2026-11-04" → "4 Nov 2026". Tanggal ISO dibaca sebagai tanggal lokal, bukan UTC. */
export function formatDate(iso: string | null | undefined): string {
  if (!iso) return '—';
  const [y, m, d] = iso.slice(0, 10).split('-').map(Number);
  return dateFormat.format(new Date(y, m - 1, d));
}

export function formatNumber(value: number | null | undefined): string {
  return value === null || value === undefined ? '—' : numberFormat.format(value);
}

/** Selisih bertanda: +3, −2, 0. */
export function formatSigned(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—';
  if (value === 0) return '0';
  return `${value > 0 ? '+' : '−'}${numberFormat.format(Math.abs(value))}`;
}

export function addDays(iso: string, days: number): string {
  const [y, m, d] = iso.split('-').map(Number);
  const value = new Date(Date.UTC(y, m - 1, d + days));
  return value.toISOString().slice(0, 10);
}

/** Jumlah hari kalender dari a ke b (b − a). */
export function daysBetween(a: string, b: string): number {
  const toUtc = (iso: string) => { const [y, m, d] = iso.split('-').map(Number); return Date.UTC(y, m - 1, d); };
  return Math.round((toUtc(b) - toUtc(a)) / 86_400_000);
}
