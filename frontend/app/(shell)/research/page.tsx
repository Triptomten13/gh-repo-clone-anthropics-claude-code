"use client";
import { useState } from "react";
import { Button, Card, Empty, ErrorBanner, Field, PageHeader, StatusBadge, Table } from "@/components/ui";
import { ago, api } from "@/lib/api";
import { useApi } from "@/lib/hooks";

const DEPTHS = [
  { id: "quick", label: "QUICK", note: "1–2 sources, extractive" },
  { id: "standard", label: "STANDARD", note: "≤3 sources, comparison, local synthesis" },
  { id: "deep", label: "DEEP", note: "≤6 sources, refinement, contradictions" },
];

export default function ResearchPage() {
  const runs = useApi<any[]>("/api/research?limit=20");
  const mons = useApi<any>("/api/monitors");
  const events = useApi<any[]>("/api/monitors/events?limit=30");
  const [q, setQ] = useState("");
  const [depth, setDepth] = useState("quick");
  const [busy, setBusy] = useState(false);
  const [res, setRes] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);
  const run = async (force = false) => {
    setBusy(true); setErr(null);
    try { setRes(await api("/api/research", { method: "POST", json: { query: q, depth, force_refresh: force } })); runs.reload(); }
    catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  };
  const open = async (id: number) => { try { setRes(await api(`/api/research/${id}`)); } catch (e) { setErr((e as Error).message); } };
  const act = async (fn: () => Promise<unknown>) => { try { await fn(); setErr(null); mons.reload(); events.reload(); } catch (e) { setErr((e as Error).message); } };
  return (
    <>
      <PageHeader kicker="Internet intelligence · official sources, cited" title="Research & Monitoring" />
      <ErrorBanner error={err} />
      <div className="grid gap-4 xl:grid-cols-[1fr_360px]">
        <div className="space-y-4">
          <Card>
            <label className="sr-only" htmlFor="rq">Research question</label>
            <textarea id="rq" rows={2} className="w-full" placeholder="What do you want to know? Sources: Wikipedia, arXiv, Crossref, GitHub, Hacker News, PyPI, OSV, NVD, Hugging Face, news feeds." value={q} onChange={(e) => setQ(e.target.value)} />
            <div className="mt-2 flex flex-wrap items-center gap-2">
              {DEPTHS.map((d) => <button key={d.id} onClick={() => setDepth(d.id)} aria-pressed={depth === d.id} title={d.note}
                className={`rounded-md border px-2.5 py-1 font-mono text-[11px] tracking-wider ${depth === d.id ? "border-violet text-ink" : "border-line-strong text-ink-3"}`}>{d.label}</button>)}
              <span className="text-[11.5px] text-ink-3">{DEPTHS.find((d) => d.id === depth)?.note}</span>
              <span className="flex-1" />
              <Button variant="primary" busy={busy} disabled={q.trim().length < 3} onClick={() => run(false)}>Research</Button>
            </div>
          </Card>
          {res ? <Card title={`${res.depth?.toUpperCase()} · ${res.status?.replaceAll("_", " ")}${res.cached ? " · from research cache" : ""}`}
            action={res.cached ? <Button onClick={() => run(true)}>Refresh now</Button> : <span className="text-[11px] text-ink-3">{res.stats?.ms} ms · {res.stats?.requests} requests · {res.model_calls} model calls</span>}>
            {res.note && <div className="mb-2 text-[12px] text-ink-3">{res.note}</div>}
            <div className="mb-1 text-[11px] uppercase tracking-wider text-ink-3">{res.answer_label}</div>
            <div className="whitespace-pre-wrap font-serif text-[15px] leading-relaxed text-ink">{res.answer || "No supported answer — see what is missing below."}</div>
            {res.missing?.length > 0 && <div className="mt-2 text-[12.5px] text-warning">Missing evidence: {res.missing.join(" · ")}</div>}
            {res.contradictions?.length > 0 && <div className="mt-3 rounded border border-warning/40 p-2 text-[12.5px]">
              <div className="mb-1 text-warning">Possible contradictions (reported, not resolved)</div>
              {res.contradictions.map((c: any, i: number) => <div key={i} className="mb-1 text-ink-2">“{c.a.claim}” vs “{c.b.claim}” <span className="text-ink-3">— {c.why}</span></div>)}
            </div>}
            {res.sources?.length > 0 && <Table head={["#", "Source", "Kind", "Published", "Score", ""]}>
              {res.sources.map((s: any) => <tr key={s.n} className="align-top"><td className="num">{s.n}</td>
                <td><a className="text-violet hover:underline" href={s.url} target="_blank" rel="noreferrer">{s.title || s.url}</a><div className="text-[11px] text-ink-3">{s.license_note}</div></td>
                <td className="text-[12px] text-ink-2">{s.source} · {s.reliability}</td><td className="num text-[12px]">{s.published_at ? String(s.published_at).slice(0, 10) : "—"}</td>
                <td className="num">{s.score}</td>
                <td><Button title="Keep this excerpt in the Archive with its provenance" onClick={() => act(() => api("/api/research/promote", { method: "POST", json: { url: s.url } }))}>Save to Archive</Button></td></tr>)}
            </Table>}
            {res.stats?.errors?.length > 0 && <div className="mt-2 text-[11.5px] text-ink-3">Source issues: {res.stats.errors.join(" · ")}</div>}
          </Card> : <Card><Empty title="No research yet">Ask a question. Quick lookups never spend more than they need; answers always carry their sources, and generated summaries are labelled as such.</Empty></Card>}
          <Card title="Recent research" pad={false}>
            {runs.data?.length ? <Table head={["Question", "Depth", "Status", "Sources", "When"]}>
              {runs.data.map((r) => <tr key={r.id} className="cursor-pointer" onClick={() => open(r.id)}><td className="max-w-md truncate">{r.query}</td><td className="font-mono text-[11px]">{r.depth}</td>
                <td><StatusBadge status={r.status === "completed" ? "completed" : r.status === "offline" ? "blocked" : "needs_review"} /></td><td className="num">{r.sources}</td><td className="text-ink-3">{ago(r.created_at)}</td></tr>)}
            </Table> : <div className="p-4 text-[12.5px] text-ink-3">None yet.</div>}
          </Card>
        </div>
        <div className="space-y-4">
          <Card title="Monitors" pad={false}>
            {mons.data?.monitors?.length ? <ul className="divide-y divide-line/60">{mons.data.monitors.map((m: any) => <li key={m.id} className="px-4 py-2 text-[12.5px]">
              <div className="flex items-center gap-2"><span className="flex-1 font-medium">{m.name}</span><StatusBadge status={m.enabled ? "active" : "disabled"} /></div>
              <div className="text-[11.5px] text-ink-3">{m.query} · {m.sources.join(", ")} · every {m.every_minutes >= 1440 ? `${m.every_minutes / 1440} d` : `${m.every_minutes} min`} · ≤{m.max_requests} requests · last {m.last_run_at ? ago(m.last_run_at) : "never"}</div>
              <div className="mt-1 flex gap-1.5"><Button onClick={() => act(() => api(`/api/monitors/${m.id}/run`, { method: "POST" }))}>Run now</Button>
                <Button onClick={() => act(() => api(`/api/monitors/${m.id}`, { method: "PATCH", json: { enabled: !m.enabled } }))}>{m.enabled ? "Pause" : "Resume"}</Button>
                <Button variant="danger" onClick={() => act(() => api(`/api/monitors/${m.id}`, { method: "DELETE" }))}>Delete</Button></div>
            </li>)}</ul> : <div className="p-4 text-[12.5px] text-ink-3">No monitors. Each one needs a purpose, a schedule and a request budget.</div>}
            <div className="border-t border-line p-3">
              <Field label="Add from a template">
                <select defaultValue="" onChange={(e) => { const t = mons.data?.templates?.[Number(e.target.value)]; if (t) act(() => api("/api/monitors", { method: "POST", json: { ...t, max_requests: 3 } })); e.target.value = ""; }}>
                  <option value="" disabled>choose…</option>
                  {(mons.data?.templates ?? []).map((t: any, i: number) => <option key={t.name} value={i}>{t.name} — {t.purpose}</option>)}
                </select>
              </Field>
            </div>
          </Card>
          <Card title="Alerts (changes only)" pad={false}>
            {events.data?.length ? <ul className="max-h-[420px] divide-y divide-line/60 overflow-auto">{events.data.map((e) => <li key={e.id} className={`px-4 py-2 text-[12.5px] ${e.acknowledged ? "opacity-60" : ""}`}>
              <div className="flex items-center gap-2"><StatusBadge status={e.kind === "change" ? "pending" : "failed"} /><span className="flex-1">{e.summary}</span>
                {!e.acknowledged && <Button onClick={() => act(() => api(`/api/monitors/events/${e.id}/ack`, { method: "POST" }))}>Ack</Button>}</div>
              {e.items?.slice(0, 4).map((it: any, i: number) => <div key={i} className="truncate text-[11.5px]"><a className="text-violet hover:underline" href={it.url} target="_blank" rel="noreferrer">{it.title}</a></div>)}
            </li>)}</ul> : <div className="p-4 text-[12.5px] text-ink-3">No changes detected. Quiet subjects produce no alerts.</div>}
          </Card>
        </div>
      </div>
    </>
  );
}
