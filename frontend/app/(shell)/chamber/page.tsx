"use client";
import Link from "next/link";
import { useState } from "react";
import { Button, Card, Empty, ErrorBanner, EvidenceBadge, Field, PageHeader, StatusBadge } from "@/components/ui";
import { ago, api, API_URL, getToken } from "@/lib/api";
import { useApi } from "@/lib/hooks";

type Step = { id: number; ordinal: number; title: string; kind: string; task_type: string; status: string; summary: string; depends_on: number[]; approval_id: number | null; task_id: number | null };
type Run = { id: number; objective: string; mode: string; status: string; intent: string; clarification: string; answer: string; answer_method: string;
  citations: any[]; contradictions: { between: string; detail: string }[]; verification: any; steps: Step[]; ai_cost_usd: number; ai_calls: number; created_at: string; trace_run_id?: number | null };

const STEP_STATUS: Record<string, string> = { completed: "succeeded", running: "running", pending: "queued", waiting_for_approval: "pending", blocked: "blocked", failed: "failed", cancelled: "cancelled" };
const EXAMPLES = ["Evaluate the winter commuter pannier and create brand concepts", "What do the sources say about the Babylonian exile?",
  "Convene a council on the hand-crank emergency radio", "Check the Archivum canon for contradictions", "Launch the roll-top stem bag", "Utvärdera nödradion"];

export default function Chamber() {
  const meta = useApi<any>("/api/gsus/modes");
  const runs = useApi<any[]>("/api/gsus/runs");
  const [objective, setObjective] = useState("");
  const [mode, setMode] = useState("gsus");
  const [tone, setTone] = useState("plain");
  const [depth, setDepth] = useState("standard");
  const [creativity, setCreativity] = useState<number | null>(null);
  const [strictness, setStrictness] = useState<number | null>(null);
  const [run, setRun] = useState<Run | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const modes = meta.data?.modes ?? {};
  const m = modes[mode];
  const llm = meta.data?.llm && meta.data.llm !== "none";

  const start = async () => {
    setBusy(true); setErr(null);
    try {
      const settings: any = { tone, depth };
      if (creativity !== null) settings.creativity = creativity;
      if (strictness !== null) settings.strictness = strictness;
      setRun(await api<Run>("/api/gsus/runs", { method: "POST", json: { objective, mode, settings } }));
      runs.reload();
    } catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  };
  const act = async (path: string) => { try { setRun(await api<Run>(path, { method: "POST" })); runs.reload(); } catch (e) { setErr((e as Error).message); } };
  const open = async (id: number) => { try { setRun(await api<Run>(`/api/gsus/runs/${id}`)); } catch (e) { setErr((e as Error).message); } };

  return (
    <>
      <PageHeader kicker="G-SUS · head orchestrator" title="The G-sus Chamber">
        <span className="flex items-center gap-1.5 text-[12px] text-ink-3"><span className={`pulse-dot inline-block h-1.5 w-1.5 rounded-full ${llm ? "bg-cyan" : "bg-ink-3"}`} />
          {llm ? `models: ${meta.data.llm}` : "no AI provider — research & orchestration still work; creative text is not faked"}</span>
      </PageHeader>
      <ErrorBanner error={err || meta.error} />
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1fr)_340px]">
        <div className="space-y-4">
          <Card>
            <label className="sr-only" htmlFor="objective">Objective</label>
            <textarea id="objective" rows={3} className="w-full font-serif text-[16px]" placeholder="State an objective. G-sus plans it, delegates it, checks it — you stay in control."
              value={objective} onChange={(e) => setObjective(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey) && objective.length > 2) start(); }} />
            <div className="mt-2 flex flex-wrap gap-1.5">{EXAMPLES.map((x) => <button key={x} onClick={() => setObjective(x)} className="min-h-7 rounded border border-line px-2.5 py-1 text-left text-[11.5px] text-ink-3 hover:border-violet-dim hover:text-ink-2 pointer-coarse:min-h-9">{x}</button>)}</div>
            <div className="mt-3 flex flex-wrap items-end gap-3">
              <Field label="Tone"><select value={tone} onChange={(e) => setTone(e.target.value)}>{(meta.data?.tones ?? []).map((t: string) => <option key={t}>{t.replace("_", " ")}</option>)}</select></Field>
              <Field label="Depth"><select value={depth} onChange={(e) => setDepth(e.target.value)}>{(meta.data?.depths ?? []).map((t: string) => <option key={t}>{t}</option>)}</select></Field>
              <Field label={`Creativity ${(creativity ?? m?.creativity ?? 0).toFixed(1)}`}><input type="range" min={0} max={1} step={0.1} value={creativity ?? m?.creativity ?? 0} onChange={(e) => setCreativity(Number(e.target.value))} /></Field>
              <Field label={`Factual strictness ${(strictness ?? m?.strictness ?? 0).toFixed(1)}`}><input type="range" min={0} max={1} step={0.1} value={strictness ?? m?.strictness ?? 0} onChange={(e) => setStrictness(Number(e.target.value))} /></Field>
              <span className="flex-1" />
              <Button variant="primary" busy={busy} disabled={objective.trim().length < 3} onClick={start}>Ask G-sus</Button>
            </div>
          </Card>

          {run ? <RunView run={run} onResume={() => act(`/api/gsus/runs/${run.id}/resume`)} onCancel={() => act(`/api/gsus/runs/${run.id}/cancel`)} />
            : <Card><Empty title="No run selected">G-sus understands the objective, asks if something is unclear, plans over the platform's real capabilities, runs agents in parallel where safe, stops for your approval on high-impact actions, compares results and verifies before answering.</Empty></Card>}
          <DeepReasoning />
          <StreamChat mode={mode} enabled={!!llm} />
        </div>

        <div className="space-y-4">
          <Card title="Mode">
            <div className="grid grid-cols-2 gap-1.5">
              {Object.entries(modes).map(([k, v]: any) => (
                <button key={k} onClick={() => { setMode(k); setCreativity(null); setStrictness(null); }}
                  className={`rounded-md border p-2 text-left ${mode === k ? "border-violet bg-violet/10" : "border-line hover:border-violet-dim"}`} aria-pressed={mode === k}>
                  <div className="font-serif text-[13.5px] text-ink">{v.title}</div>
                  <div className="text-[10.5px] leading-snug text-ink-3">{v.essence}</div>
                  <div className="mt-1 font-mono text-[9.5px] uppercase text-ink-3">{v.creative ? "creative · labelled" : "research · grounded"}</div>
                </button>
              ))}
            </div>
          </Card>
          <Card title="Recent runs" pad={false}>
            {runs.data?.length ? <ul className="max-h-[420px] divide-y divide-line/60 overflow-auto">{runs.data.map((r) => (
              <li key={r.id}><button onClick={() => open(r.id)} className="w-full px-4 py-2 text-left hover:bg-surface-2/60">
                <div className="truncate text-[12.5px] text-ink-2">{r.objective}</div>
                <div className="mt-0.5 flex items-center gap-2 text-[11px] text-ink-3"><StatusBadge status={STEP_STATUS[r.status] ?? r.status} />{r.mode} · {ago(r.created_at)}</div>
              </button></li>))}</ul> : <div className="p-4 text-[12.5px] text-ink-3">No runs yet.</div>}
          </Card>
        </div>
      </div>
    </>
  );
}

function RunView({ run, onResume, onCancel }: { run: Run; onResume: () => void; onCancel: () => void }) {
  return (
    <Card title={`Run #${run.id} · ${run.mode} · ${run.status.replaceAll("_", " ")}`} action={<span className="num text-[11.5px] text-ink-3">{run.ai_calls} model calls · ${run.ai_cost_usd.toFixed(4)}</span>}>
      {run.status === "needs_clarification" && <div className="mb-3 rounded-md border border-warning/50 bg-warning/10 px-3 py-2 text-[13px] text-ink">G-sus asks: {run.clarification}</div>}
      {run.steps.length > 0 && (
        <ol className="mb-4 space-y-1.5" aria-label="plan">
          {run.steps.map((s) => (
            <li key={s.id} className="flex items-start gap-2 text-[12.5px]">
              <span className="num mt-0.5 w-5 text-right text-ink-3">{s.ordinal + 1}</span>
              <StatusBadge status={STEP_STATUS[s.status] ?? s.status} />
              <div className="min-w-0 flex-1">
                <div className="text-ink">{s.title} <span className="font-mono text-[10.5px] text-ink-3">{s.task_type || s.kind}{s.depends_on.length ? ` ← ${s.depends_on.map((d) => d + 1).join(",")}` : ""}</span></div>
                {s.summary && <div className="text-[12px] text-ink-3">{s.summary}</div>}
                {s.approval_id && s.status === "waiting_for_approval" && <Link href="/approvals" className="text-[12px] text-violet hover:underline">Decide approval #{s.approval_id} →</Link>}
              </div>
            </li>
          ))}
        </ol>
      )}
      {run.status === "waiting_for_approval" && <div className="mb-3 flex gap-2"><Button variant="primary" onClick={onResume}>Resume after decision</Button><Button variant="danger" onClick={onCancel}>Cancel run</Button></div>}
      {run.trace_run_id && <p className="mb-3 text-[12px]"><Link href={`/governance#runs/${run.trace_run_id}`} className="text-violet hover:underline">Trace &amp; replay · run #{run.trace_run_id} →</Link></p>}
      {run.contradictions?.length > 0 && (
        <div className="mb-3 rounded-md border border-serious/40 bg-serious/5 p-3">
          <div className="mb-1 font-mono text-[10.5px] uppercase tracking-[0.14em] text-serious">Contradictions & tensions</div>
          <ul className="space-y-1 text-[12.5px] text-ink-2">{run.contradictions.map((c, i) => <li key={i}><b className="text-ink">{c.between}:</b> {c.detail}</li>)}</ul>
        </div>
      )}
      {run.answer && <pre className="whitespace-pre-wrap rounded-md bg-bg p-3 font-serif text-[13.5px] leading-relaxed text-ink-2">{run.answer}</pre>}
      {run.citations?.length > 0 && (
        <div className="mt-3">
          <div className="mb-1 font-mono text-[10.5px] uppercase tracking-[0.14em] text-gold">Sources</div>
          <ol className="space-y-1.5">{run.citations.map((c) => (
            <li key={c.n} className="text-[12px]"><span className="num text-ink-3">[{c.n}]</span> <Link href={`/knowledge#doc-${c.document_id}`} className="text-ink hover:text-violet">{c.title}</Link> §{c.ordinal}{c.page ? ` p.${c.page}` : ""} <EvidenceBadge kind={c.evidence_class} />
              {c.injection_risk && <span className="ml-1 text-warning">⚠ instruction-like text (treated as data)</span>}{c.source && <span className="text-ink-3"> · {c.source}</span>}</li>))}</ol>
        </div>
      )}
      {run.verification?.steps !== undefined && <div className="mt-3 text-[11.5px] text-ink-3">Verification: {run.verification.completed?.length ?? 0}/{run.verification.steps} steps completed{run.verification.retrieval_grounded === false ? " · retrieval NOT fully grounded" : ""}</div>}
    </Card>
  );
}

function StreamChat({ mode, enabled }: { mode: string; enabled: boolean }) {
  const [msg, setMsg] = useState("");
  const [out, setOut] = useState("");
  const [sources, setSources] = useState<any[]>([]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const send = async () => {
    setBusy(true); setOut(""); setSources([]); setErr(null);
    try {
      const res = await fetch(`${API_URL}/api/gsus/chat/stream`, { method: "POST", headers: { "Content-Type": "application/json", Authorization: `Bearer ${getToken()}` }, body: JSON.stringify({ message: msg, mode }) });
      if (!res.ok || !res.body) { setErr((await res.json().catch(() => ({ detail: res.statusText }))).detail); return; }
      const reader = res.body.getReader(); const dec = new TextDecoder(); let buf = "";
      for (;;) {
        const { value, done } = await reader.read(); if (done) break;
        buf += dec.decode(value, { stream: true });
        const events = buf.split("\n\n"); buf = events.pop() ?? "";
        for (const ev of events) {
          const type = /^event: (\w+)/m.exec(ev)?.[1] ?? "message"; const data = /^data: (.*)$/m.exec(ev)?.[1];
          if (!data) continue;
          const d = JSON.parse(data);
          if (type === "sources") setSources(d); else if (type === "error") setErr(d.error); else if (d.text) setOut((o) => o + d.text);
        }
      }
    } catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  };
  return (
    <Card title="Conversation (streaming)">
      {!enabled ? <Empty title="Conversation needs an AI provider">Set ANTHROPIC_API_KEY or OLLAMA_BASE_URL. Runs above still work without one.</Empty> : (
        <>
          <div className="flex gap-2"><input className="flex-1" value={msg} onChange={(e) => setMsg(e.target.value)} placeholder="Talk to G-sus in the selected mode…" /><Button variant="primary" busy={busy} disabled={!msg} onClick={send}>Send</Button></div>
          <ErrorBanner error={err} />
          {out && <pre className="mt-3 whitespace-pre-wrap font-serif text-[13.5px] text-ink-2">{out}</pre>}
          {sources.length > 0 && <div className="mt-2 text-[11.5px] text-ink-3">Archive context: {sources.map((s) => `[${s.n}] ${s.title} (${s.evidence})`).join(" · ")}</div>}
        </>
      )}
    </Card>
  );
}

/** Deep reasoning: the deep tier (local reasoning model first) through /api/ai/reason. The model's working notes are
 *  shown separately, labelled unverified; an answer concluded after the thinking budget ran out is flagged. */
function DeepReasoning() {
  const status = useApi<any>("/api/ai/status");
  const [q, setQ] = useState("");
  const [ctx, setCtx] = useState("");
  const [verify, setVerify] = useState(false);
  const [samples, setSamples] = useState(1);
  const [busy, setBusy] = useState(false);
  const [res, setRes] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);
  const [secs, setSecs] = useState(0);
  const deepModel = status.data?.active_models?.deep;
  const ask = async () => {
    setBusy(true); setErr(null); setRes(null);
    const t0 = Date.now();
    const timer = setInterval(() => setSecs(Math.round((Date.now() - t0) / 1000)), 1000);
    try { setRes(await api("/api/ai/reason", { method: "POST", json: { question: q, context: ctx, verify, samples } })); }
    catch (e) { setErr((e as Error).message); }
    finally { clearInterval(timer); setSecs(Math.round((Date.now() - t0) / 1000)); setBusy(false); }
  };
  return (
    <Card title="Deep reasoning" action={<span className="text-[11.5px] text-ink-3">{deepModel ? `local: ${deepModel}` : "no local reasoning model — DAEMON CORE → Models"}</span>}>
      <label className="sr-only" htmlFor="deep-q">Question</label>
      <textarea id="deep-q" rows={3} className="w-full" placeholder="A problem that needs several steps of reasoning — pricing, logistics, logic, trade-offs…" value={q} onChange={(e) => setQ(e.target.value)} />
      <label className="sr-only" htmlFor="deep-ctx">Context</label>
      <textarea id="deep-ctx" rows={2} className="mt-2 w-full text-[12.5px]" placeholder="Optional context (treated as untrusted data, never as instructions)" value={ctx} onChange={(e) => setCtx(e.target.value)} />
      <div className="mt-2 flex flex-wrap items-center gap-3">
        <label className="flex items-center gap-1.5 text-[12.5px] text-ink-2">Self-consistency
          <select value={samples} onChange={(e) => setSamples(Number(e.target.value))} aria-label="Number of reasoning samples">
            <option value={1}>off (1 sample)</option><option value={3}>3 samples · majority vote</option><option value={5}>5 samples · majority vote</option>
          </select></label>
        <label className="flex items-center gap-1.5 text-[12.5px] text-ink-2"><input type="checkbox" checked={verify} onChange={(e) => setVerify(e.target.checked)} />Second opinion from another model</label>
        <span className="flex-1" />
        {busy && <span className="num text-[12px] text-ink-3">thinking… {secs}s</span>}
        <Button variant="primary" busy={busy} disabled={q.trim().length < 5} onClick={ask}>Reason</Button>
      </div>
      <p className="mt-1 text-[11.5px] text-ink-3">On this CPU a local reasoning model thinks for one to several minutes per sample. A single sample can be confidently wrong — use self-consistency for anything that matters. The thinking budget is set in DAEMON settings.</p>
      <ErrorBanner error={err} />
      {res && <div className="mt-3 space-y-2 border-t border-line pt-3">
        <div className="flex flex-wrap items-center gap-2 text-[11.5px] text-ink-3">
          <span className="font-mono">{res.provider}:{res.model}</span><span>· {secs}s</span>
          {res.reasoning_complete === false ? <StatusBadge status="needs_review" /> : res.reasoning ? <StatusBadge status="completed" /> : null}
          {res.reasoning_complete === false && <span className="text-warning">thinking budget reached — answer concluded from incomplete reasoning, lower confidence</span>}
          {res.self_consistency && <span className={res.self_consistency.majority ? "text-good" : "text-warning"}>
            {res.self_consistency.majority ? `samples agree ${res.self_consistency.agreement}` : `NO majority (${res.self_consistency.agreement}) — unreliable`}</span>}
        </div>
        <div className="whitespace-pre-wrap font-serif text-[15px] leading-relaxed text-ink" data-testid="deep-answer"><LiteText text={res.answer} /></div>
        {res.reasoning && <details className="rounded border border-line bg-bg/60 p-2">
          <summary className="cursor-pointer text-[12px] text-ink-3">Working notes ({res.reasoning.length.toLocaleString()} characters) — the model&apos;s own, unverified</summary>
          <pre className="mt-2 max-h-80 overflow-auto whitespace-pre-wrap font-mono text-[11.5px] text-ink-2">{res.reasoning}</pre>
        </details>}
        {res.verification && <div className="rounded border border-line p-2 text-[12.5px]">
          <div className="mb-1 text-[11.5px] text-ink-3">Second opinion · {res.verification.provider}:{res.verification.model}{res.verification.independent ? "" : " (not independent)"}</div>
          <div className="whitespace-pre-wrap text-ink-2">{res.verification.answer ?? res.verification.error}</div>
          <div className="mt-1 text-[11px] text-ink-3">{res.verification.note}</div>
        </div>}
      </div>}
    </Card>
  );
}

/** Minimal, safe rendering of model markdown: **bold** becomes <strong> (React elements, never HTML injection) and
 *  inline-math markers are simplified ($ 180 \times 0.25 $ → 180 × 0.25). Everything else stays plain text. */
function LiteText({ text }: { text: string }) {
  const clean = text.replace(/\\times/g, "×").replace(/\\cdot/g, "·").replace(/\$\s?([^$\n]+?)\s?\$/g, "$1");
  return <>{clean.split(/(\*\*[^*\n]+\*\*)/g).map((part, i) =>
    part.startsWith("**") && part.endsWith("**") && part.length > 4 ? <strong key={i} className="font-semibold">{part.slice(2, -2)}</strong> : <span key={i}>{part}</span>)}</>;
}
