"use client";
/** Demo Center — the approved sample workflows. Every button calls the REAL endpoint as the signed-in user; the
 *  result shown is exactly what came back (or the refusal). The API enforces every limit, not this page. */
import Link from "next/link";
import { useState } from "react";
import { Button, Card, ErrorBanner, PageHeader, SourceLabel, StatusBadge } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { useApi } from "@/lib/hooks";

type Workflow = { key: string; kind: "gsus" | "ask" | "plan" | "evals" | "tool"; title: string; shows: string; expect: string;
  objective?: string; mode?: string; question?: string; tool?: string; args?: Record<string, unknown> };
type Catalog = { demo_mode: boolean; workflows: Workflow[]; actions_left: number | null; reset_hours: number | null; labels: Record<string, string> };
type Outcome = { ok: boolean; status: string; summary: string; source: string[]; link?: { href: string; label: string }; detail?: unknown; approvalId?: number };

async function execute(w: Workflow): Promise<Outcome> {
  try {
    if (w.kind === "gsus") {
      const r = await api<any>("/api/gsus/runs", { method: "POST", json: { objective: w.objective, mode: w.mode } });
      const gate = r.steps?.find((s: any) => s.kind === "approval_gate" && s.approval_id);
      const done = r.steps?.filter((s: any) => s.status === "completed").length ?? 0;
      return { ok: true, status: r.status, approvalId: gate?.approval_id,
        summary: `G-sus run #${r.id}: ${r.steps?.length ?? 0} step(s), ${done} completed${r.contradictions?.length ? `, ${r.contradictions.length} contradiction(s) reported` : ""}${gate ? ` — waiting for approval #${gate.approval_id}` : ""}.`,
        source: ["demo", r.answer_method === "llm" ? "connected" : "rules"],
        link: r.trace_run_id ? { href: `/governance#runs/${r.trace_run_id}`, label: `Trace & replay · run #${r.trace_run_id}` } : undefined,
        detail: r.answer ? r.answer.slice(0, 1200) : r.clarification };
    }
    if (w.kind === "ask") {
      const r = await api<any>("/api/ai/ask", { method: "POST", json: { question: w.question } });
      return { ok: true, status: "succeeded", summary: `Answer: ${r.answer ?? "—"} · strategy ${r.plan?.strategy ?? r.method ?? "?"} · ${r.model_calls ?? 0} model call(s) · ${r.latency_ms ?? "?"} ms`,
        source: ["live", r.model_calls ? "connected" : "rules"],
        link: r.run_id ? { href: `/governance#runs/${r.run_id}`, label: `Trace & replay · run #${r.run_id}` } : undefined, detail: r.plan ?? r.trace };
    }
    if (w.kind === "plan") {
      const r = await api<any>("/api/ai/plan", { method: "POST", json: { question: w.question } });
      const why = r.plan?.reason ? ` — ${r.plan.reason}` : "";
      return { ok: true, status: "succeeded", summary: `Category “${r.classification?.category ?? "?"}” → strategy “${r.plan?.strategy ?? "?"}”${why}. Nothing was executed.`,
        source: ["rules"], detail: r };
    }
    if (w.kind === "evals") {
      const r = await api<any>("/api/ai/evals/run", { method: "POST" });
      return { ok: true, status: "succeeded", summary: r.suites.map((s: any) => `${s.suite} ${s.score ?? "—"}`).join(" · "), source: ["live", "rules"], detail: r.suites };
    }
    await api<any>(`/api/tools/${w.tool}/invoke`, { method: "POST", json: { args: w.args } });
    return { ok: false, status: "failed", summary: "The tool ran — this demo session should not have been allowed to use it.", source: ["live"] };
  } catch (e) {
    const err = e as ApiError;
    if (w.expect === "403" && err.status === 403) return { ok: true, status: "blocked", summary: `Refused by the backend, as it must be: ${err.message}`, source: ["live"] };
    return { ok: false, status: err.status === 429 ? "blocked" : "failed", summary: err.message, source: ["live"] };
  }
}

export default function DemoCenter() {
  const cat = useApi<Catalog>("/api/demo/catalog");
  const [out, setOut] = useState<Record<string, Outcome>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const run = async (w: Workflow) => {
    setBusy(w.key);
    const o = await execute(w);
    setOut((m) => ({ ...m, [w.key]: o }));
    setBusy(null);
    cat.reload();
  };
  const tryApprove = async (w: Workflow, id: number) => {
    setBusy(w.key + ":approve");
    let o: Outcome;
    try {
      await api(`/api/approvals/${id}/decide`, { method: "POST", json: { approve: true, note: "attempt from a demo session" } });
      o = { ok: false, status: "failed", summary: "The approval went through — a demo session must never be able to approve.", source: ["live"] };
    } catch (e) {
      o = { ok: (e as ApiError).status === 403, status: "blocked", summary: `Approval refused by the backend: ${(e as Error).message}`, source: ["live"] };
    }
    setOut((m) => ({ ...m, [w.key + ":approve"]: o }));
    setBusy(null);
  };
  const c = cat.data;
  return (
    <>
      <PageHeader kicker="Public demo" title="Demo Center">
        {c?.actions_left != null && <span className="num text-[12px] text-ink-3">{c.actions_left} action(s) left in this session</span>}
      </PageHeader>
      <ErrorBanner error={cat.error} />
      <p className="mb-4 max-w-3xl text-[13.5px] text-ink-2">
        Each workflow runs the real backend as your temporary demo session — real agents, orchestration, policies and
        retrieval on synthetic sample data. Refusals are real refusals. {c?.reset_hours ? `The demo database is reset every ${c.reset_hours} hours.` : ""}
      </p>
      {c && (
        <div className="mb-5 flex flex-wrap gap-x-4 gap-y-2 text-[12px] text-ink-3" aria-label="Labels">
          {Object.entries({ live: "LIVE DATA", demo: "DEMO DATA", rules: "RULE-BASED", simulated: "SIMULATED OUTPUT", connected: "CONNECTED SERVICE", unavailable: "UNAVAILABLE SERVICE" }).map(([k, name]) => (
            <span key={k} className="inline-flex items-center gap-1.5"><SourceLabel kind={k} /> {c.labels[name] ?? "computed by rules, not by an AI model"}</span>
          ))}
        </div>
      )}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {c?.workflows.map((w) => {
          const o = out[w.key];
          const ap = out[w.key + ":approve"];
          return (
            <Card key={w.key} title={w.title}>
              <p className="mb-3 text-[13px] text-ink-2">{w.shows}</p>
              {(w.objective || w.question) && <p className="mb-3 font-mono text-[12px] text-ink-3">“{w.objective || w.question}”{w.mode && w.mode !== "gsus" ? ` · mode ${w.mode}` : ""}</p>}
              <Button variant="primary" busy={busy === w.key} disabled={!!busy} onClick={() => run(w)}>Run</Button>
              {o && (
                <div role="status" className="mt-3 rounded-md border border-line bg-bg/50 p-3 text-[13px]">
                  <div className="mb-1.5 flex flex-wrap items-center gap-2"><StatusBadge status={o.status} />{o.source.map((s) => <SourceLabel key={s} kind={s} />)}
                    {!o.ok && <span className="text-warning">unexpected result</span>}</div>
                  <p className="break-words">{o.summary}</p>
                  {o.link && <Link href={o.link.href} className="mt-1.5 inline-block text-[12.5px] text-violet hover:underline">{o.link.label} →</Link>}
                  {typeof o.detail === "string" && <pre className="mt-2 max-h-48 overflow-auto whitespace-pre-wrap break-words font-mono text-[11.5px] text-ink-3">{o.detail}</pre>}
                  {o.approvalId && (
                    <div className="mt-3 border-t border-line pt-3">
                      <Button busy={busy === w.key + ":approve"} disabled={!!busy} onClick={() => tryApprove(w, o.approvalId!)}>Try to approve it yourself</Button>
                      {ap && <p className="mt-2 flex flex-wrap items-center gap-2"><StatusBadge status={ap.status} /><span className="break-words">{ap.summary}</span></p>}
                    </div>
                  )}
                </div>
              )}
            </Card>
          );
        })}
      </div>
    </>
  );
}
