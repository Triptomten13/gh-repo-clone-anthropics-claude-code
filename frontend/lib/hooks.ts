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
