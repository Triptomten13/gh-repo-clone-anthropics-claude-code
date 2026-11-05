"use client";
import { useState } from "react";
import { Button, Card, Empty, ErrorBanner, PageHeader, Stat, StatusBadge, Table } from "@/components/ui";
import { ago, api } from "@/lib/api";
import { useApi } from "@/lib/hooks";

export default function AICore() {
  const prov = useApi<any>("/api/ai/providers");
  const models = useApi<any>("/api/ai/models");
  const usage = useApi<any>("/api/ai/usage?days=30");
  const calls = useApi<any[]>("/api/ai/calls?limit=40");
  const evals = useApi<any[]>("/api/ai/evals");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const run = async (llm: boolean) => { setBusy(true); try { await api(`/api/ai/evals/run?include_llm=${llm}`, { method: "POST" }); evals.reload(); } catch (e) { setErr((e as Error).message); } finally { setBusy(false); } };
  const u = usage.data;
  const last = evals.data?.[0];
  return (
    <>
      <PageHeader kicker="Demonkoncernen · AI infrastructure" title="AI Core" />
      <ErrorBanner error={err} />
      <div className="mb-4 grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label="Active providers" value={<span className="text-lg">{prov.data?.active ?? "…"}</span>} sub={prov.data?.llm_enabled === false ? "LLM disabled by config" : ""} />
        <Stat label="Spend today" value={u ? `$${u.spent_today_usd.toFixed(4)}` : "…"} sub={u ? `cap $${u.daily_cost_limit_usd}/day` : ""} accent />
        <Stat label="Calls (30 d)" value={u?.calls ?? "…"} sub={u ? `$${u.cost_usd.toFixed(4)} at list prices` : ""} />
        <Stat label="Embeddings" value={<span className="text-[13px]">{prov.data?.embeddings.active ?? "…"}</span>} sub={prov.data?.embeddings.note} />
      </div>
      <div className="grid gap-4 xl:grid-cols-2">
        <Card title="Provider health" pad={false}>
          <Table head={["Provider", "Configured", "Circuit", "Last OK", "Last error"]}>
            {(prov.data?.llm ?? []).map((p: any) => <tr key={p.provider}><td className="font-medium">{p.provider}</td>
              <td><StatusBadge status={p.configured ? "configured" : "missing_credentials"} /></td><td><StatusBadge status={p.state === "open" ? "blocked" : "active"} /> <span className="text-[11px] text-ink-3">{p.state}</span></td>
              <td className="text-ink-3">{p.last_ok ? ago(new Date(p.last_ok * 1000).toISOString()) : "—"}</td><td className="max-w-xs truncate text-[12px] text-ink-3" title={p.last_error}>{p.last_error ?? "—"}</td></tr>)}
          </Table>
          <div className="p-3 text-[11.5px] text-ink-3">Tier chains: {Object.entries(models.data?.chains ?? {}).map(([t, c]: any) => `${t} → ${c.map((x: any) => x.join(":")).join(" ▸ ")}`).join(" · ")}. Unavailable providers fall back down the chain; refusals never do.</div>
        </Card>
        <Card title="Evaluations" action={<span className="flex gap-2"><Button busy={busy} onClick={() => run(false)}>Run evals</Button><Button busy={busy} onClick={() => run(true)} title="Uses the configured model; costs money">+ LLM suite</Button></span>}>
          {last ? (
            <Table head={["Suite", "Cases", "Score", "Details"]}>{last.suites.map((s: any) => <tr key={s.suite}><td className="font-medium">{s.suite.replaceAll("_", " ")}</td><td className="num">{s.cases ?? "—"}</td>
              <td className="num">{s.skipped ? <span className="text-ink-3">skipped</span> : s.score}</td>
              <td className="text-[11.5px] text-ink-3">{s.skipped ? s.reason : [s.metric, s.precision !== undefined && `P ${s.precision} R ${s.recall}`, s.recall_at_3 !== undefined && `recall@3 ${s.recall_at_3}, labels ${s.evidence_label_accuracy}, abstention ${s.abstention_on_unanswerable}`, s.failures?.length && `${s.failures.length} failures`].filter(Boolean).join(" · ")}</td></tr>)}</Table>
          ) : <Empty title="No evaluations yet">Run the suites to measure planner accuracy, injection detection, the anti-generic gate and retrieval grounding.</Empty>}
          {last && <div className="mt-2 text-[11.5px] text-ink-3">Ran {last.ran_at} in {last.duration_s}s</div>}
        </Card>
      </div>
      <Card title="Model registry" className="mt-4" pad={false}>
        <Table head={["Model", "Provider", "Capabilities", "Context", "Max out", "$ in / out per MTok", "Use", "Available"]}>
          {(models.data?.models ?? []).map((m: any) => <tr key={m.provider + m.model_id} className="align-top"><td><div className="font-medium">{m.display_name}</div><code className="text-[11px] text-ink-3">{m.model_id}</code></td>
            <td className="text-ink-2">{m.provider}</td><td className="max-w-xs text-[11.5px] text-ink-3">{m.capabilities.join(", ")}</td>
            <td className="num">{m.context_window ? `${(m.context_window / 1000).toLocaleString()}K` : "—"}</td><td className="num">{m.max_output_tokens ? `${m.max_output_tokens / 1000}K` : "—"}</td>
            <td className="num">{m.input_usd_per_mtok === null ? "—" : `${m.input_usd_per_mtok} / ${m.output_usd_per_mtok}`}</td><td className="max-w-xs text-[11.5px] text-ink-3">{m.intended_use}{m.notes && <div>{m.notes}</div>}</td>
            <td><StatusBadge status={m.available ? "configured" : "missing_credentials"} /></td></tr>)}
        </Table>
      </Card>
      <div className="mt-4 grid gap-4 xl:grid-cols-2">
        <Card title="Usage by model (30 days)" pad={false}>
          {u && Object.keys(u.by_model).length ? <Table head={["Model", "Calls", "OK", "Tokens in/out", "Cost", "Avg latency"]}>{Object.entries(u.by_model).map(([k, v]: any) => <tr key={k}><td className="font-mono text-[12px]">{k}</td><td className="num">{v.calls}</td><td className="num">{v.status_ok ?? 0}</td><td className="num">{v.input_tokens}/{v.output_tokens}</td><td className="num">${v.cost_usd}</td><td className="num">{v.avg_latency_ms ?? "—"} ms</td></tr>)}</Table>
            : <div className="p-4"><Empty title="No model calls recorded">Calls appear here (with failed and fallback attempts) as soon as a provider is configured and used.</Empty></div>}
        </Card>
        <Card title="Recent calls (trace)" pad={false}>
          {calls.data?.length ? <Table head={["When", "Agent", "Purpose", "Provider:model", "Status", "$"]}>{calls.data.map((c) => <tr key={c.id}><td className="text-ink-3">{ago(c.created_at)}</td><td>{c.agent_id}</td><td className="text-[12px] text-ink-3">{c.purpose}</td><td className="font-mono text-[11.5px]">{c.provider}:{c.model}</td><td><StatusBadge status={c.status === "ok" ? "succeeded" : c.status === "refused" ? "blocked" : "failed"} /></td><td className="num">{c.cost_usd}</td></tr>)}</Table>
            : <div className="p-4 text-[12.5px] text-ink-3">No traces yet.</div>}
        </Card>
      </div>
    </>
  );
}
