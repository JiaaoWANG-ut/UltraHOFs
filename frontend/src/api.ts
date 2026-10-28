export type Json = Record<string, any>;

const BASE = '/api/v1';
const ACCESS = 'uh_access';
const REFRESH = 'uh_refresh';

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

export const tokens = {
  get access() {
    return localStorage.getItem(ACCESS);
  },
  get refresh() {
    return localStorage.getItem(REFRESH);
  },
  set(access: string, refresh?: string) {
    localStorage.setItem(ACCESS, access);
    if (refresh) localStorage.setItem(REFRESH, refresh);
  },
  clear() {
    localStorage.removeItem(ACCESS);
    localStorage.removeItem(REFRESH);
  },
};

let refreshing: Promise<boolean> | null = null;

async function tryRefresh(): Promise<boolean> {
  const rt = tokens.refresh;
  if (!rt) return false;
  if (!refreshing) {
    refreshing = fetch(`${BASE}/auth/refresh`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: rt }),
    })
      .then(async (r) => {
        if (!r.ok) return false;
        const d = await r.json();
        tokens.set(d.access_token);
        return true;
      })
      .catch(() => false)
      .finally(() => {
        setTimeout(() => (refreshing = null), 0);
      });
  }
  return refreshing;
}

interface Opts {
  json?: unknown;
  query?: Record<string, unknown>;
  form?: FormData;
  text?: boolean;
}

function qs(query?: Record<string, unknown>) {
  if (!query) return '';
  const p = new URLSearchParams();
  Object.entries(query).forEach(([k, v]) => {
    if (v === undefined || v === null || v === '') return;
    if (Array.isArray(v)) v.forEach((x) => p.append(k, String(x)));
    else p.set(k, String(v));
  });
  const s = p.toString();
  return s ? `?${s}` : '';
}

async function request<T = any>(method: string, path: string, opts: Opts = {}, retry = true): Promise<T> {
  const headers: Record<string, string> = {};
  if (tokens.access) headers.Authorization = `Bearer ${tokens.access}`;
  let body: BodyInit | undefined;
  if (opts.json !== undefined) {
    headers['Content-Type'] = 'application/json';
    body = JSON.stringify(opts.json);
  } else if (opts.form) {
    body = opts.form;
  }
  const res = await fetch(`${BASE}${path}${qs(opts.query)}`, { method, headers, body });
  if (res.status === 401 && retry && !path.startsWith('/auth/login')) {
    if (await tryRefresh()) return request<T>(method, path, opts, false);
    tokens.clear();
    window.dispatchEvent(new Event('auth:logout'));
  }
  if (!res.ok) {
    let msg = `${res.status} ${res.statusText}`;
    try {
      const d = await res.json();
      if (typeof d.detail === 'string') msg = d.detail;
      else if (Array.isArray(d.detail)) msg = d.detail.map((x: Json) => `${(x.loc || []).slice(-1)[0]}: ${x.msg}`).join('; ');
    } catch {
      /* not json */
    }
    throw new ApiError(res.status, msg);
  }
  if (opts.text) return (await res.text()) as T;
  return (await res.json()) as T;
}

export const api = {
  get: <T = any>(path: string, query?: Record<string, unknown>) => request<T>('GET', path, { query }),
  text: (path: string, query?: Record<string, unknown>) => request<string>('GET', path, { query, text: true }),
  post: <T = any>(path: string, json?: unknown) => request<T>('POST', path, { json: json ?? {} }),
  patch: <T = any>(path: string, json?: unknown) => request<T>('PATCH', path, { json }),
  del: <T = any>(path: string) => request<T>('DELETE', path),
  upload: <T = any>(path: string, form: FormData) => request<T>('POST', path, { form }),
  async download(path: string, query: Record<string, unknown>, filename: string) {
    const text = await request<string>('GET', path, { query, text: true });
    const blob = new Blob([text], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 2000);
  },
};
