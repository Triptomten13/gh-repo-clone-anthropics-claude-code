"use client";
import { useState } from "react";
import { api } from "./api";

export type Task = { id: number; status: string; result: any; error: string | null; type: string };

/** Run a Rocky Flare agent task through the orchestrator and return the finished task. */
export function useRun() {
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const run = async (type: string, payload: Record<string, unknown>): Promise<Task | null> => {
    setBusy(type); setError(null);
    try {
      let t = await api<Task>("/api/flare/run", { method: "POST", json: { type, payload } });
      for (let i = 0; i < 30 && (t.status === "queued" || t.status === "running"); i++) {
        await new Promise((r) => setTimeout(r, 700));
        t = await api<Task>(`/api/tasks/${t.id}`);
      }
      if (t.status !== "succeeded") setError(`${type}: ${t.status}${t.error ? ` — ${t.error.split("\n")[0]}` : ""}`);
      return t;
    } catch (e) { setError((e as Error).message); return null; }
    finally { setBusy(null); }
  };
  return { run, busy, error, setError };
}

export const svgSrc = (svg: string) => `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;
export const label = (s: string) => s.replaceAll("_", " ");
