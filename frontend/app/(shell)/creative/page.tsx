"use client";
/** CREATIVE INTELLIGENCE CENTER — Creative Tournament Mode, routing decisions, model profiles, provider health, costs.
 *  Every number comes from the backend; a tournament runs on the server under its hard budget and stop conditions. */
import Link from "next/link";
import { useEffect, useState } from "react";
import { Button, Card, Empty, Epistemic, ErrorBanner, Field, PageHeader, SourceLabel, StatusBadge, Table } from "@/components/ui";
import { ago, api } from "@/lib/api";
import { useApi } from "@/lib/hooks";

const TABS = [["tournaments", "Tournaments"], ["routing", "Routing"], ["models", "Model quality"], ["providers", "Providers & health"], ["costs", "Costs"]] as const;
const T_STATUS: Record<string, string> = { completed: "completed", stopped: "needs_review", failed: "failed", running: "running", ready: "queued", pending_approval: "pending" };
const E_STATUS: Record<string, string> = { ok: "succeeded", failed: "failed", rejected: "rejected" };
const pctv = (v: number | null | undefined) => (v == null ? "—" : `${Math.round(v * 100)}`);

export default function Creative() {
  const [tab, setTab] = useState<string>("tournaments");
  useEffect(() => { const h = window.location.hash.slice(1).split("/")[0]; if (TABS.some(([id]) => id === h)) setTab(h); }, []);
  const pick = (t: string) => { setTab(t); history.replaceState(null, "", `#${t}`); };
  return (
    <>
      <PageHeader kicker="G-SUS · creative intelligence" title="Creative Intelligence Center">
        <span className="text-[12px] text-ink-3">many models compete, independent critics judge, one synthesis — inside a hard budget</span>
      </PageHeader>
      <div role="tablist" aria-label="Creative intelligence sections" className="mb-4 flex flex-wrap gap-1">
        {TABS.map(([id, name]) => <button key={id} role="tab" aria-selected={tab === id} onClick={() => pick(id)}
          className={`min-h-9 rounded-md border px-3 text-[12.5px] ${tab === id ? "border-violet bg-violet/10 text-ink" : "border-line text-ink-3 hover:text-ink-2"}`}>{name}</button>)}
      </div>
      {tab === "tournaments" ? <Tournaments /> : tab === "routing" ? <Routing /> : tab === "models" ? <Models /> : tab === "providers" ? <Providers /> : <Costs />}
    </>
  );
}

// ------------------------------------------------------------------ tournaments
function Tournaments() {
  const list = useApi<any[]>("/api/creative/tournaments");
  const ov = useApi<any>("/api/creative/overview");
  const [sel, setSel] = useState<number | null>(null);
  useEffect(() => { const m = /^#t-(\d+)$/.exec(window.location.hash); if (m) setSel(Number(m[1])); }, []);  // deep link from search
  const [brief, setBrief] = useState("");
  const [adv, setAdv] = useState(false);
  const [f, setF] = useState({ strategy: "AUTOMATIC", mode: "FREE_FIRST", quality_target: 0.75, max_calls: 8, max_models: 3, critics: 2, max_rounds: 1,
    max_usd: 0, max_seconds: 900, classification: "INTERNAL", allow_parallel: true });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const set = (k: string, v: unknown) => setF((x) => ({ ...x, [k]: v }));
  const start = async () => {
    setBusy(true); setErr(null); setNote(null);
    try {
      const body = adv ? { brief, strategy: f.strategy, mode: f.mode, quality_target: f.quality_target, classification: f.classification, allow_parallel: f.allow_parallel,
        budget: { max_calls: f.max_calls, max_models: f.max_models, critics: f.critics, max_rounds: f.max_rounds, max_usd: f.max_usd, max_seconds: f.max_seconds } } : { brief };
      const r = await api<any>("/api/creative/tournaments", { method: "POST", json: body });
      if (r.status === "pending_approval") setNote(`Waiting for approval #${r.approval_id}: ${r.reason}`);
      setSel(r.id ?? r.tournament); list.reload();
    } catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  };
  return (
    <div className="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,380px)_minmax(0,1fr)]">
      <div className="min-w-0 space-y-4">
        <Card title="New tournament">
          <ErrorBanner error={err} />
          {note && <div role="status" className="mb-3 rounded-md border border-warning/40 bg-warning/10 px-3 py-2 text-[13px] text-warning">{note} — decide it in the <Link className="underline" href="/approvals">Approval Center</Link>, then start again with the same settings.</div>}
          <label htmlFor="brief" className="mb-1 block text-[12px] text-ink-3">Brief</label>
          <textarea id="brief" rows={4} className="w-full" value={brief} onChange={(e) => setBrief(e.target.value)}
            placeholder="Skriv en låt om vinterns första snö i en norrländsk by — vers och refräng." />
          <button className="mt-2 text-[12px] text-violet underline-offset-2 hover:underline" aria-expanded={adv} onClick={() => setAdv((a) => !a)}>
            {adv ? "Hide advanced settings" : "Advanced settings (otherwise: AUTOMATIC)"}</button>
          {adv && (
            <div className="mt-3 grid grid-cols-2 gap-3">
              <Field label="Strategy"><select value={f.strategy} onChange={(e) => set("strategy", e.target.value)}>{(ov.data?.strategies ?? ["AUTOMATIC"]).map((s: string) => <option key={s}>{s}</option>)}</select></Field>
              <Field label="Routing mode"><select value={f.mode} onChange={(e) => set("mode", e.target.value)}>{Object.keys(ov.data?.modes ?? { FREE_FIRST: 1 }).map((m) => <option key={m}>{m}</option>)}</select></Field>
              <Field label={`Quality target ${f.quality_target.toFixed(2)}`}><input type="range" min={0.3} max={1} step={0.05} value={f.quality_target} onChange={(e) => set("quality_target", Number(e.target.value))} /></Field>
              <Field label="Data class"><select value={f.classification} onChange={(e) => set("classification", e.target.value)}>{["PUBLIC", "INTERNAL", "CONFIDENTIAL", "RESTRICTED", "HIGHLY_SENSITIVE"].map((c) => <option key={c}>{c}</option>)}</select></Field>
              <Field label="Max contestants"><input type="number" min={1} max={6} value={f.max_models} onChange={(e) => set("max_models", Number(e.target.value))} /></Field>
              <Field label="Critics"><input type="number" min={0} max={3} value={f.critics} onChange={(e) => set("critics", Number(e.target.value))} /></Field>
              <Field label="Max model calls"><input type="number" min={1} max={40} value={f.max_calls} onChange={(e) => set("max_calls", Number(e.target.value))} /></Field>
              <Field label="Revision rounds"><input type="number" min={0} max={4} value={f.max_rounds} onChange={(e) => set("max_rounds", Number(e.target.value))} /></Field>
              <Field label="Max paid USD"><input type="number" min={0} step={0.05} value={f.max_usd} onChange={(e) => set("max_usd", Number(e.target.value))} /></Field>
              <Field label="Time limit (s)"><input type="number" min={10} max={3600} value={f.max_seconds} onChange={(e) => set("max_seconds", Number(e.target.value))} /></Field>
              <label className="col-span-2 flex items-center gap-2 text-[12.5px] text-ink-2"><input type="checkbox" checked={f.allow_parallel} onChange={(e) => set("allow_parallel", e.target.checked)} /> Run remote models in parallel (local models always run one after another)</label>
            </div>
          )}
          <p className="mt-3 text-[12px] text-ink-3">Stops when the quality target is reached, the budget or time runs out, or a round improves by less than 0.02. Paid spending above ${ov.data?.autonomous_usd?.toFixed(2) ?? "0.50"} needs an approval.</p>
          <div className="mt-3"><Button variant="primary" busy={busy} disabled={brief.trim().length < 3} onClick={start}>Start tournament</Button></div>
        </Card>
        <Card title="Recent tournaments" pad={false}>
          <ErrorBanner error={list.error} />
          {list.data?.length ? (
            <ul className="divide-y divide-line">{list.data.map((t) => (
              <li key={t.id}><button onClick={() => setSel(t.id)} className={`w-full px-4 py-2.5 text-left hover:bg-surface-2 ${sel === t.id ? "bg-surface-2" : ""}`}>
                <div className="flex flex-wrap items-center gap-2 text-[12px]"><span className="font-mono text-violet">#{t.id}</span><StatusBadge status={T_STATUS[t.status] ?? t.status} />
                  <span className="text-ink-3">{t.strategy} · {t.category}</span><span className="num ml-auto text-ink-3">{pctv(t.final_score)}</span></div>
                <div className="mt-0.5 truncate text-[13px]">{t.brief}</div>
              </button></li>))}</ul>
          ) : <div className="p-4"><Empty title="No tournaments yet">Start one with a brief — a song, a name list, a business idea.</Empty></div>}
        </Card>
      </div>
      <div className="min-w-0">{sel ? <TournamentView id={sel} onChange={list.reload} /> : <Card><Empty title="Select or start a tournament" /></Card>}</div>
    </div>
  );
}

function TournamentView({ id, onChange }: { id: number; onChange: () => void }) {
  const t = useApi<any>(`/api/creative/tournaments/${id}`, [id]);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState<string | null>(null);
  const live = t.data && ["ready", "running"].includes(t.data.status);
  useEffect(() => {
    if (!live) return;
    const h = setInterval(() => { t.reload(); onChange(); }, 2500);
    return () => clearInterval(h);
  }, [live]); // eslint-disable-line react-hooks/exhaustive-deps
  const d = t.data;
  if (!d) return <Card><ErrorBanner error={t.error} />{!t.error && <p className="text-[13px] text-ink-3">Loading…</p>}</Card>;
  const result = d.entries.find((e: any) => e.id === d.result_entry_id);
  const save = async () => {
    setSaving(true);
    try { const r = await api<any>(`/api/creative/tournaments/${id}/save`, { method: "POST" }); setSaved(`Saved to the Archive as document #${r.document_id} (model-generated).`); }
    catch (e) { setSaved((e as Error).message); } finally { setSaving(false); }
  };
  return (
    <div className="space-y-4">
      <Card title={`Tournament #${d.id} · ${d.strategy} · ${d.routing_mode}`} action={<StatusBadge status={T_STATUS[d.status] ?? d.status} />}>
        <p className="mb-2 font-serif text-[15px]">{d.brief}</p>
        {live && <p role="status" className="mb-2 text-[13px] text-cyan">Running — {d.entries.length} output(s) so far…</p>}
        {d.stop_reason && <p className="mb-2 text-[13px] text-ink-2"><span className="text-ink-3">Stopped: </span>{d.stop_reason}</p>}
        <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-[12.5px] sm:grid-cols-4">
          <div><dt className="text-ink-3">Final score</dt><dd className="num">{pctv(d.final_score)} / target {pctv(d.quality_target)}</dd></div>
          <div><dt className="text-ink-3">Model calls</dt><dd className="num">{d.usage?.calls ?? 0} of {d.budget?.max_calls}</dd></div>
          <div><dt className="text-ink-3">Tokens · cost</dt><dd className="num">{d.usage?.tokens ?? 0} · ${(d.usage?.usd ?? 0).toFixed(4)}</dd></div>
          <div><dt className="text-ink-3">Time</dt><dd className="num">{d.usage?.seconds ?? "—"} s</dd></div>
          {d.usage?.creative_value_per_resource_unit != null && <div className="col-span-2"><dt className="text-ink-3">Creative value per resource unit</dt><dd className="num">{d.usage.creative_value_per_resource_unit}</dd></div>}
          {d.usage?.gain_per_extra_call != null && <div className="col-span-2"><dt className="text-ink-3">Gain per extra call after round 1</dt><dd className="num">{d.usage.gain_per_extra_call >= 0 ? "+" : ""}{d.usage.gain_per_extra_call}</dd></div>}
        </dl>
        {d.plan?.selection && <p className="mt-2 text-[12px] text-ink-3">{d.plan.why}. {d.plan.selection}</p>}
        <div className="mt-3 flex flex-wrap gap-3 text-[12.5px]">
          {d.trace_run_id && <Link className="text-violet hover:underline" href={`/governance#runs/${d.trace_run_id}`}>Trace & replay →</Link>}
          {result && !d.saved_document_id && <Button busy={saving} onClick={save}>Save to the Archive</Button>}
          {(saved || d.saved_document_id) && <span className="text-ink-3">{saved ?? `Saved as document #${d.saved_document_id}`}</span>}
        </div>
      </Card>
      {result && (
        <Card title="Result" action={<span className="flex items-center gap-2"><SourceLabel kind={result.model_id.startsWith("local:") ? "live" : "connected"} /><span className="font-mono text-[11px] text-ink-3">{result.role} · {result.model_id}</span></span>}>
          <pre className="whitespace-pre-wrap break-words font-serif text-[15px] leading-relaxed text-ink">{result.text}</pre>
          {d.alternatives?.length > 1 && <p className="mt-3 text-[12px] text-ink-3">Alternatives: {d.alternatives.map((a: any) => `${a.label} (#${a.entry})`).join(" · ")}</p>}
        </Card>
      )}
      <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
        {d.entries.map((e: any) => <EntryCard key={e.id} e={e} accepted={e.id === d.result_entry_id} />)}
      </div>
    </div>
  );
}

function EntryCard({ e, accepted }: { e: any; accepted: boolean }) {
  const checks = Object.entries(e.deterministic?.checks ?? {}) as [string, number][];
  return (
    <section className={`min-w-0 rounded-lg border p-3 ${accepted ? "border-violet" : "border-line"} bg-surface`}>
      <div className="mb-2 flex flex-wrap items-center gap-2 text-[12px]">
        <span className="font-mono text-ink-3">#{e.id} · r{e.round} · {e.role}</span><StatusBadge status={E_STATUS[e.status] ?? e.status} />
        {accepted && <span className="rounded border border-violet px-1.5 font-mono text-[10px] text-violet">ACCEPTED</span>}
        <span className="num ml-auto">{pctv(e.score)}</span>
      </div>
      <div className="mb-2 truncate font-mono text-[11.5px] text-cyan" title={e.model_id}>{e.model_id}{e.latency_ms ? ` · ${(e.latency_ms / 1000).toFixed(1)} s` : ""}</div>
      {e.error && <p className="mb-2 text-[12px] text-warning">{e.error}</p>}
      {e.text && <pre className="mb-2 max-h-48 overflow-auto whitespace-pre-wrap break-words font-serif text-[13px] text-ink-2">{e.text}</pre>}
      {checks.length > 0 && <div className="mb-1 flex flex-wrap gap-1">{checks.map(([k, v]) => <span key={k} className="rounded border border-line px-1.5 font-mono text-[10.5px] text-ink-3">{k} {Math.round(v * 100)}</span>)}</div>}
      {e.deterministic?.notes?.length > 0 && <p className="text-[11.5px] text-ink-3">Rule checks: {e.deterministic.notes.join("; ")}</p>}
      {(e.critiques ?? []).map((c: any, i: number) => (
        <div key={i} className="mt-2 border-t border-line pt-2 text-[11.5px] text-ink-3">
          <span className="font-mono text-ink-2">critic {c.critic}</span> · {Object.entries(c.scores).map(([k, v]) => `${k} ${v}`).join(", ")}
          {c.best_lines?.length > 0 && <div>Best: “{c.best_lines.join("” · “")}”</div>}
          {c.weaknesses?.length > 0 && <div>Weak: {c.weaknesses.join("; ")}</div>}
        </div>
      ))}
    </section>
  );
}

// ------------------------------------------------------------------ routing
function Routing() {
  const ov = useApi<any>("/api/creative/overview");
  const [brief, setBrief] = useState("Skriv en låt om vinterns första snö med refräng");
  const [mode, setMode] = useState("FREE_FIRST");
  const [cls, setCls] = useState("INTERNAL");
  const [res, setRes] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);
  const run = async () => { setErr(null); try { setRes(await api("/api/creative/select", { method: "POST", json: { brief, mode, classification: cls, n: 3 } })); } catch (e) { setErr((e as Error).message); } };
  return (
    <div className="space-y-4">
      <Card title="Which models would do this — and why">
        <ErrorBanner error={err} />
        <div className="grid grid-cols-1 gap-3 md:grid-cols-[minmax(0,1fr)_180px_160px_auto] md:items-end">
          <Field label="Task"><input value={brief} onChange={(e) => setBrief(e.target.value)} /></Field>
          <Field label="Routing mode"><select value={mode} onChange={(e) => setMode(e.target.value)}>{Object.keys(ov.data?.modes ?? { FREE_FIRST: 1 }).map((m) => <option key={m}>{m}</option>)}</select></Field>
          <Field label="Data class"><select value={cls} onChange={(e) => setCls(e.target.value)}>{["PUBLIC", "INTERNAL", "CONFIDENTIAL", "RESTRICTED", "HIGHLY_SENSITIVE"].map((c) => <option key={c}>{c}</option>)}</select></Field>
          <Button variant="primary" onClick={run}>Decide</Button>
        </div>
        {ov.data?.modes?.[mode] && <p className="mt-2 text-[12px] text-ink-3">{mode}: {ov.data.modes[mode]}</p>}
      </Card>
      {res && (
        <Card title={`${res.task.category} · ${res.task.language} · ${res.task.complexity} complexity`} pad={false}>
          <p className="px-4 pt-3 text-[13px]">{res.explanation}</p>
          <Table head={["#", "Model", "Score", "Quality", "Cost class", "Per call", "Why"]} label="Ranked models">
            {res.ranked.map((r: any, i: number) => (
              <tr key={r.model} className="align-top"><td className="num">{i + 1}</td><td className="font-mono text-[12px]">{r.model}</td><td className="num">{r.score}</td>
                <td className="num">{pctv(r.quality)}{r.stale_profile && <span className="ml-1 text-warning">stale</span>}</td><td>{r.candidate.cost_class.replace("_", " ")}</td>
                <td className="num">{r.est_cost_usd ? `$${r.est_cost_usd.toFixed(4)}` : "—"}</td><td className="max-w-md text-[12px] text-ink-3">{r.why}</td></tr>))}
          </Table>
          {res.excluded.length > 0 && <div className="border-t border-line p-4 text-[12.5px] text-ink-3"><div className="mb-1 text-ink-2">Not allowed or not possible here</div>
            <ul className="space-y-0.5">{res.excluded.map((x: any) => <li key={x.model}><span className="font-mono">{x.model}</span> — {x.why}</li>)}</ul></div>}
        </Card>
      )}
    </div>
  );
}

// ------------------------------------------------------------------ model quality
function Models() {
  const m = useApi<any>("/api/creative/models");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const bench = async (models: string[]) => {
    setBusy(true);
    try { await api("/api/creative/benchmarks", { method: "POST", json: { models } }); setMsg(`Benchmark started for ${models.length} model(s) — scores appear here when it finishes.`); }
    catch (e) { setMsg((e as Error).message); } finally { setBusy(false); }
  };
  const d = m.data;
  return (
    <div className="space-y-4">
      <ErrorBanner error={m.error} />
      <Card title={`Measured quality by task (dataset ${d?.dataset ?? "…"})`} pad={false}>
        {d?.models?.length ? (
          <Table head={["Model", "Cost class", ...(d.categories ?? [])]} label="Model quality">
            {d.models.map((x: any) => (
              <tr key={x.model}><td className="font-mono text-[12px]">{x.model}</td><td>{x.cost_class.replace("_", " ")}</td>
                {d.categories.map((c: string) => { const s = x.scores[c]; return <td key={c} className="num">{s ? <span title={`${s.tasks} task(s), ${s.latency_ms ?? "?"} ms`}>{pctv(s.score)}{s.stale && <span className="ml-1 text-warning" title="model changed since">*</span>}</span> : <span className="text-ink-3">—</span>}</td>; })}
              </tr>))}
          </Table>
        ) : <div className="p-4"><Empty title="No models available" /></div>}
        <p className="p-3 text-[12px] text-ink-3">{d?.note} Scores 0–100 from rule-based checks on fixed tasks; * = the model changed since it was measured.</p>
      </Card>
      <Card title="Needs (re-)benchmarking">
        {msg && <p role="status" className="mb-2 text-[13px] text-ink-2">{msg}</p>}
        {d?.due?.length ? (<>
          <ul className="mb-3 space-y-1 text-[13px]">{d.due.map((x: any) => <li key={x.model}><span className="font-mono text-[12px]">{x.model}</span> — <span className="text-ink-3">{x.reason}</span></li>)}</ul>
          <Button busy={busy} onClick={() => bench(d.due.filter((x: any) => x.model.startsWith("local:")).map((x: any) => x.model))}>Benchmark the local ones</Button>
          <p className="mt-2 text-[12px] text-ink-3">Runs {d.tasks?.length ?? 10} tasks per model on this machine; local models take minutes on a CPU. External models are benchmarked only when you choose them (they cost money).</p>
        </>) : <p className="text-[13px] text-ink-3">Every available model has a current profile.</p>}
      </Card>
    </div>
  );
}

// ------------------------------------------------------------------ providers & health
function Providers() {
  const p = useApi<any>("/api/creative/providers");
  const disc = useApi<any>("/api/creative/discovery");
  return (
    <div className="space-y-4">
      <ErrorBanner error={p.error || disc.error} />
      <Card title="Models this deployment can use" pad={false}>
        {p.data && (
          <Table head={["Model", "Where", "Cost class", "Approved", "Usable now", "Calls 24 h", "Error rate", "p50 latency"]} label="Models">
            {p.data.models.map((m: any) => {
              // approved for routing is not the same as usable: an API model needs its provider's key on this server
              const configured = p.data.runtimes.find((r: any) => r.provider === m.provider)?.configured ?? false;
              const excluded = m.last_24h?.excluded ?? 0;
              return (
              <tr key={m.id}><td className="font-mono text-[12px]">{m.id}</td><td>{m.locality}</td><td>{m.cost_class.replace("_", " ")}</td>
                <td><StatusBadge status={m.approved ? "approved" : "unverified"} /></td>
                <td><StatusBadge status={configured ? "configured" : "missing_credentials"} /></td>
                <td className="num">{m.last_24h?.calls ?? 0}{excluded ? <span className="text-ink-3" title="not configured, paused, over a spend limit, breaker open or excluded by policy"> ({excluded} not sent)</span> : null}</td>
                <td className="num">{m.last_24h?.error_rate != null ? `${Math.round(m.last_24h.error_rate * 100)} %` : "—"}</td>
                <td className="num">{m.last_24h?.p50_latency_ms != null ? `${(m.last_24h.p50_latency_ms / 1000).toFixed(1)} s` : "—"}</td></tr>);
            })}
          </Table>
        )}
      </Card>
      <Card title="Runtimes (circuit breakers)" pad={false}>
        {p.data && <Table head={["Provider", "Where", "Configured", "Breaker", "Last error"]} label="Runtimes">
          {p.data.runtimes.map((r: any) => <tr key={r.provider}><td>{r.provider}</td><td>{r.locality}</td><td>{r.configured ? "yes" : "no"}</td>
            <td><StatusBadge status={r.state === "open" ? "blocked" : "operational"} /></td><td className="max-w-xs truncate text-[12px] text-ink-3">{r.last_error ?? "—"}</td></tr>)}
        </Table>}
      </Card>
      <Card title="Discovery — candidates, never routable until validated">
        {disc.data && (<>
          <p className="mb-2 text-[12.5px] text-ink-3">Path to routing: {disc.data.validation_path.join(" → ")}</p>
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            <div><h3 className="mb-1 text-[13px] font-medium">Providers not verified ({disc.data.unverified_providers.length})</h3>
              <ul className="space-y-1 text-[12.5px] text-ink-3">{disc.data.unverified_providers.map((x: any) => <li key={x.id}>{x.name} — unknown: {x.missing.join(", ") || "—"}</li>)}</ul></div>
            <div><h3 className="mb-1 text-[13px] font-medium">Catalogued local models not installed ({disc.data.catalog_not_installed.length})</h3>
              <ul className="space-y-1 text-[12.5px] text-ink-3">{disc.data.catalog_not_installed.map((x: any) => <li key={x.key}>{x.name} · {x.size_gb} GB · {x.licence} ({x.commercial_use.replace("_", " ")})</li>)}</ul></div>
          </div>
          <p className="mt-3 text-[12px] text-ink-3">{p.data?.note}</p>
        </>)}
      </Card>
    </div>
  );
}

// ------------------------------------------------------------------ costs
function Costs() {
  const c = useApi<any>("/api/creative/costs");
  const d = c.data;
  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
      <ErrorBanner error={c.error} />
      <Card title={`Model usage, last ${d?.days ?? 30} days`} pad={false}>
        {d && <Table head={["Where", "Calls", "Tokens", "USD"]} label="Usage by locality">
          {Object.entries(d.by_locality).map(([k, v]: [string, any]) => <tr key={k}><td>{k}</td><td className="num">{v.calls}</td><td className="num">{v.tokens}</td><td className="num">${v.usd.toFixed(4)}</td></tr>)}
        </Table>}
        {d?.estimated_savings_usd != null && <p className="p-3 text-[12.5px] text-ink-2"><Epistemic kind="estimate" /> <span className="ml-1">Estimated savings ${d.estimated_savings_usd.toFixed(4)} — {d.estimated_savings_note}</span></p>}
      </Card>
      <Card title="Tournaments">
        {d && <dl className="grid grid-cols-2 gap-3 text-[13px]">
          <div><dt className="text-ink-3">Run · reached target</dt><dd className="num">{d.tournaments.count} · {d.tournaments.accepted}</dd></div>
          <div><dt className="text-ink-3">Model calls · tokens</dt><dd className="num">{d.tournaments.calls} · {d.tournaments.tokens}</dd></div>
          <div><dt className="text-ink-3">Paid spend</dt><dd className="num">${d.tournaments.usd.toFixed(4)}</dd></div>
          <div><dt className="text-ink-3">Paid USD per result at target</dt><dd className="num">{d.tournaments.usd_per_accepted_result != null ? `$${d.tournaments.usd_per_accepted_result.toFixed(4)}` : "—"}</dd></div>
          <div className="col-span-2"><dt className="text-ink-3">Average creative value per resource unit</dt><dd className="num">{d.tournaments.avg_creative_value_per_resource_unit ?? "—"}</dd></div>
        </dl>}
        <p className="mt-3 text-[12px] text-ink-3">Value per resource unit = final score ÷ (1 + tokens/10 000 + USD/0.01 + minutes). Local inference has no API price but uses electricity — see DAEMON CORE → Costs.</p>
      </Card>
    </div>
  );
}
