const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || '/api/v1').replace(/\/$/, '');

/* Error API dengan pesan `detail` dari FastAPI agar bisa langsung ditampilkan ke pengguna. */
export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

type ValidationIssue = { loc?: (string | number)[]; msg?: string };

async function errorMessage(response: Response): Promise<string> {
  try {
    const body = await response.json() as { detail?: string | ValidationIssue[] };
    if (typeof body.detail === 'string') return body.detail;
    if (Array.isArray(body.detail)) return body.detail.map((d) => `${(d.loc ?? []).slice(1).join('.')}: ${d.msg ?? ''}`).join('; ');
  } catch { /* respons bukan JSON */ }
  return `API mengembalikan status ${response.status}`;
}

async function request<T>(method: string, path: string, body?: unknown, signal?: AbortSignal): Promise<T> {
  const headers: Record<string, string> = { Accept: 'application/json' };
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  const response = await fetch(`${API_BASE_URL}${path}`, { method, signal, headers, body: body === undefined ? undefined : JSON.stringify(body) });
  if (!response.ok) throw new ApiError(response.status, await errorMessage(response));
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export function apiGet<T>(path: string, signal?: AbortSignal): Promise<T> {
  return request<T>('GET', path, undefined, signal);
}

export function apiPost<T>(path: string, body?: unknown): Promise<T> {
  return request<T>('POST', path, body ?? {});
}

export function apiPut<T>(path: string, body: unknown): Promise<T> {
  return request<T>('PUT', path, body);
}

export function apiDelete(path: string): Promise<void> {
  return request<void>('DELETE', path);
}
