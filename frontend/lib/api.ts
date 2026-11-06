"use client";

/** "" = same origin (default): the web server proxies /api, /ws and /health to the backend (next.config.ts), so the
 *  app works unchanged from a phone on the LAN or behind HTTPS. Set NEXT_PUBLIC_API_URL only for a separate API host. */
export const API_URL = (process.env.NEXT_PUBLIC_API_URL || "").replace(/\/$/, "");
const TOKEN_KEY = "rocky.token";

export function getToken(): string | null {
  try { return localStorage.getItem(TOKEN_KEY); } catch { return null; }
}
export function setToken(t: string | null, demo = false) {
  try {
    t ? localStorage.setItem(TOKEN_KEY, t) : localStorage.removeItem(TOKEN_KEY);
    demo && t ? localStorage.setItem(DEMO_KEY, "1") : localStorage.removeItem(DEMO_KEY);
  } catch { /* storage unavailable */ }
}

/** A public-demo visitor session (POST /api/demo/session). Only changes wording — every limit is enforced by the API. */
const DEMO_KEY = "rocky.demo";
export function isDemoSession(): boolean {
  try { return localStorage.getItem(DEMO_KEY) === "1"; } catch { return false; }
}

/** Start a temporary public-demo session (demo servers only). */
export async function startDemoSession(): Promise<void> {
  const r = await api<{ token: string }>("/api/demo/session", { method: "POST" });
  setToken(r.token, true);
}

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

/** Reads time out (a phone on a bad network must not spin forever); writes do not by default, because AI work —
 *  deep reasoning, research — legitimately takes minutes. Pass timeoutMs to override. */
const READ_TIMEOUT_MS = 30_000;

export async function api<T = any>(path: string, init: RequestInit & { json?: unknown; timeoutMs?: number } = {}): Promise<T> {
  const headers = new Headers(init.headers);
  const tok = getToken();
  if (tok) headers.set("Authorization", `Bearer ${tok}`);
  let body = init.body;
  if (init.json !== undefined) { headers.set("Content-Type", "application/json"); body = JSON.stringify(init.json); }
  const method = (init.method || "GET").toUpperCase();
  const timeout = init.timeoutMs ?? (method === "GET" ? READ_TIMEOUT_MS : 0);
  const ctrl = new AbortController();
  const timer = timeout ? setTimeout(() => ctrl.abort(), timeout) : undefined;
  init.signal?.addEventListener("abort", () => ctrl.abort());
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, { ...init, headers, body, signal: ctrl.signal });
  } catch (e) {
    if (init.signal?.aborted) throw e;
    throw new ApiError(0, ctrl.signal.aborted ? `The server did not answer within ${Math.round(timeout / 1000)} s` :
      "Cannot reach the Demonkoncernen server — check the connection");
  } finally {
    clearTimeout(timer);
  }
  if (res.status === 401 && typeof window !== "undefined" && !path.startsWith("/api/auth")) {
    setToken(null);
    window.location.href = "/login";
  }
  if (!res.ok) {
    let msg = res.statusText;
    try { const j = await res.json(); msg = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail ?? j); } catch { /* not json */ }
    if (res.status === 403 && isDemoSession()) msg = `Not available in the public demo (${msg})`;
    throw new ApiError(res.status, msg);
  }
  return res.json();
}


export const sek = (v: number | null | undefined, digits = 0) =>
  v === null || v === undefined ? "—" : new Intl.NumberFormat("sv-SE", { style: "currency", currency: "SEK", maximumFractionDigits: digits }).format(v);
export const pct = (v: number | null | undefined, digits = 0) => (v === null || v === undefined ? "—" : `${(v * 100).toFixed(digits)}%`);
export const fmt = (v: number | null | undefined, digits = 1) => (v === null || v === undefined ? "—" : v.toFixed(digits));
export const ago = (iso?: string | null) => {
  if (!iso) return "—";
  const s = (Date.now() - new Date(iso.endsWith("Z") || iso.includes("+") ? iso : iso + "Z").getTime()) / 1000;
  if (s < 60) return `${Math.max(0, Math.floor(s))}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
};
