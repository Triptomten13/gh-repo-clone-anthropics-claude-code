"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api";
import { subscribe, type LiveEvent, type LiveStatus } from "./live";

export type { LiveEvent, LiveStatus };

export function useApi<T>(path: string | null, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const reload = useCallback(async () => {
    if (!path) return;
    setLoading(true);
    try { setData(await api<T>(path)); setError(null); }
    catch (e) { setError((e as Error).message); }
    finally { setLoading(false); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path, ...deps]);
  useEffect(() => { reload(); }, [reload]);
  return { data, error, loading, reload, setData };
}

export type Me = { email: string; role: string; permissions: string[] };
let meCache: { token: string | null; p: Promise<Me | null> } | null = null;

/** The signed-in user with their permissions — one request per sign-in, shared by every component that asks.
 *  Used to show only the actions a person may take; the server enforces the same permissions on every call. */
export function useMe(): Me | null {
  const [me, setMe] = useState<Me | null>(null);
  useEffect(() => {
    let token: string | null = null;
    try { token = localStorage.getItem("rocky.token"); } catch { /* storage unavailable */ }
    if (!meCache || meCache.token !== token) meCache = { token, p: api<Me>("/api/auth/me").catch(() => null) };
    let live = true;
    meCache.p.then((m) => { if (live) setMe(m); });
    return () => { live = false; };
  }, []);
  return me;
}

/** Subscribe to the live agent event stream (one shared connection per tab — see lib/live.ts). */
export function useLiveEvents(onEvent?: (e: LiveEvent) => void, max = 80) {
  const [events, setEvents] = useState<LiveEvent[]>([]);
  const [status, setStatus] = useState<LiveStatus>("connecting");
  const cb = useRef(onEvent);
  cb.current = onEvent;
  useEffect(() => subscribe((ev) => {
    setEvents((prev) => [ev, ...prev].slice(0, max));
    cb.current?.(ev);
  }, setStatus), [max]);
  return { events, connected: status === "live", status };
}

/** Debounced reload trigger for pages that should refresh when agents finish tasks. */
export function useRefreshOn(types: string[], reload: () => void) {
  const t = useRef<ReturnType<typeof setTimeout> | null>(null);
  return useLiveEvents((e) => {
    if (!types.includes(e.type)) return;
    if (t.current) clearTimeout(t.current);
    t.current = setTimeout(reload, 400);
  });
}
