"use client";
/** ONE live-event connection per browser tab, shared by every component that listens.
 *
 *  Transport: GET /api/events/stream (text/event-stream) read with fetch, so the token goes in the Authorization header
 *  (not the URL) and the stream passes through any HTTP proxy — the web server's same-origin proxy, a TLS reverse proxy,
 *  a phone on the LAN. One shared connection matters: on HTTP/1.1 a browser allows only 6 connections per host, and
 *  every open stream holds one.
 *  Mobile: the stream pauses 30 s after the tab is hidden (battery, radio) and resumes when it is visible again or the
 *  network comes back; reconnects back off from 2 s to 30 s. */
import { API_URL, getToken } from "./api";

export type LiveEvent = { type: string; ts: string; [k: string]: any };
export type LiveStatus = "connecting" | "live" | "offline" | "paused";

const listeners = new Set<(e: LiveEvent) => void>();
const statusListeners = new Set<(s: LiveStatus) => void>();
let status: LiveStatus = "offline";
let ctrl: AbortController | null = null;
let retry: ReturnType<typeof setTimeout> | undefined;
let pauseTimer: ReturnType<typeof setTimeout> | undefined;
let backoff = 2000;
let wired = false;

function setStatus(s: LiveStatus) {
  status = s;
  statusListeners.forEach((l) => l(s));
}

export function parseFrames(buf: string): { events: LiveEvent[]; rest: string } {
  const events: LiveEvent[] = [];
  let i: number;
  while ((i = buf.indexOf("\n\n")) >= 0) {
    const frame = buf.slice(0, i);
    buf = buf.slice(i + 2);
    const data = frame.split("\n").filter((l) => l.startsWith("data:")).map((l) => l.slice(5).trimStart()).join("\n");
    if (!data) continue; // comments (": keepalive") and retry fields
    try { events.push(JSON.parse(data)); } catch { /* a malformed frame is skipped, not fatal */ }
  }
  return { events, rest: buf };
}

async function connect() {
  clearTimeout(retry);
  if (ctrl || listeners.size + statusListeners.size === 0) return;
  const tok = getToken();
  if (!tok) return setStatus("offline");
  if (document.visibilityState === "hidden") return setStatus("paused");
  const c = new AbortController();
  ctrl = c;
  setStatus("connecting");
  try {
    const res = await fetch(`${API_URL}/api/events/stream`, { headers: { Authorization: `Bearer ${tok}`, Accept: "text/event-stream" }, signal: c.signal, cache: "no-store" });
    if (res.status === 401) { ctrl = null; return setStatus("offline"); } // signed out / revoked: api() handles the redirect
    if (!res.ok || !res.body) throw new Error(`HTTP ${res.status}`);
    setStatus("live");
    backoff = 2000;
    const reader = res.body.getReader();
    const dec = new TextDecoder();
    let buf = "";
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      const parsed = parseFrames(buf + dec.decode(value, { stream: true }));
      buf = parsed.rest;
      parsed.events.forEach((ev) => listeners.forEach((l) => l(ev)));
    }
  } catch {
    if (c.signal.aborted) return; // closed on purpose (paused / no listeners)
  } finally {
    if (ctrl === c) ctrl = null;
  }
  setStatus("offline");
  retry = setTimeout(connect, backoff);
  backoff = Math.min(backoff * 2, 30000);
}

function disconnect(next: LiveStatus) {
  clearTimeout(retry);
  ctrl?.abort();
  ctrl = null;
  setStatus(next);
}

function wire() {
  if (wired || typeof window === "undefined") return;
  wired = true;
  document.addEventListener("visibilitychange", () => {
    clearTimeout(pauseTimer);
    if (document.visibilityState === "hidden") pauseTimer = setTimeout(() => disconnect("paused"), 30000);
    else connect();
  });
  window.addEventListener("online", () => { backoff = 2000; connect(); });
  window.addEventListener("offline", () => disconnect("offline"));
}

export function subscribe(onEvent: (e: LiveEvent) => void, onStatus?: (s: LiveStatus) => void): () => void {
  wire();
  listeners.add(onEvent);
  if (onStatus) { statusListeners.add(onStatus); onStatus(status); }
  connect();
  return () => {
    listeners.delete(onEvent);
    if (onStatus) statusListeners.delete(onStatus);
    if (listeners.size === 0) disconnect("offline");
  };
}

export const liveStatus = () => status;
