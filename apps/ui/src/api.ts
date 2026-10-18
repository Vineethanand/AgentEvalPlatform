// Thin wrapper over the NestJS API. All numbers shown in the UI are computed server-side.
export const API = (import.meta.env.VITE_API_URL as string | undefined) ?? 'http://localhost:3000';

export async function api<T = any>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API}${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
  });
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`);
  return res.json();
}

export const post = <T = any>(path: string, body: unknown) => api<T>(path, { method: 'POST', body: JSON.stringify(body ?? {}) });

export const pct = (x: number | null | undefined) => (x === null || x === undefined || Number.isNaN(x) ? '–' : `${(x * 100).toFixed(1)}%`);
export const pts = (x: number | null | undefined) => (x === null || x === undefined || Number.isNaN(x) ? '–' : `${x >= 0 ? '+' : ''}${(x * 100).toFixed(1)} pts`);
export const usd = (x: number | null | undefined) => (x === null || x === undefined || Number.isNaN(x) ? '–' : `$${x.toFixed(4)}`);
