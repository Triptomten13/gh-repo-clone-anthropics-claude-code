"use client";
import Link from "next/link";
import { Fragment, useEffect, useState } from "react";
import { Button, Card, Empty, Epistemic, ErrorBanner, Field, Json, PageHeader, StatusBadge, Table } from "@/components/ui";
import { ago, api } from "@/lib/api";
import { useApi, useRefreshOn } from "@/lib/hooks";

const LEVELS = ["0 research", "1 analysis", "2 drafting", "3 internal ops", "4 publish*", "5 financial*"];

export default function AgentsPage() {
  const agents = useApi<any[]>("/api/agents");
  // deep links: ?agent=<id> narrows the queue to one agent; ?task=<id> opens that task (from search, alerts, approvals)
  const [focusAgent, setFocusAgent] = useState<string | null>(null);
  const [focusTask, setFocusTask] = useState<number | null>(null);
  useEffect(() => {
    const p = new URLSearchParams(window.location.search);
    setFocusAgent(p.get("agent")); setFocusTask(Number(p.get("task")) || null);
  }, []);
  useEffect(() => { if (focusAgent) document.getElementById(`agent-${focusAgent}`)?.scrollIntoView({ block: "center" }); }, [focusAgent, agents.data]);
  const tasks = useApi<any[]>(`/api/tasks?limit=60${focusAgent ? `&agent_id=${encodeURIComponent(focusAgent)}` : ""}`, [focusAgent]);
  const msgs = useApi<any[]>("/api/messages?limit=40");
  const types = useApi<Record<string, string>>("/api/task-types");
  const { events, connected } = useRefreshOn(["task"], () => { agents.reload(); tasks.reload(); msgs.reload(); });
  const [err, setErr] = useState<string | null>(null);
  const [ttype, setTtype] = useState("");
  const [payload, setPayload] = useState("{}");
  const [open, setOpen] = useState<number | null>(null);
  const clearFocus = () => { setFocusAgent(null); setFocusTask(null); history.replaceState(null, "", "/agents"); };

  const patch = async (id: string, body: Record<string, unknown>) => {
    try { await api(`/api/agents/${id}`, { method: "PATCH", json: body }); agents.reload(); } catch (e) { setErr((e as Error).message); }
  };
  const submit = async () => {
    try { await api("/api/tasks", { method: "POST", json: { type: ttype, payload: JSON.parse(payload || "{}"), force: true } }); tasks.reload(); }
    catch (e) { setErr((e as Error).message); }
  };

  return (
    <>
      <PageHeader kicker="Agent control room" title="The organisation at work">
        <span className={`text-[12px] ${connected ? "text-good" : "text-ink-3"}`}>● {connected ? "live" : "offline"}</span>
      </PageHeader>
      <ErrorBanner error={err || agents.error} />
      {focusTask && <Card title={`Task #${focusTask}`} className="mb-4" action={<button className="text-[12px] text-ink-3 hover:text-ink" onClick={clearFocus}>close</button>}><TaskDetail id={focusTask} /></Card>}

      <Card title="Agents" pad={false}>
        <Table head={["Agent", "Division", "Level", "Status", "Queue", "OK / blocked / failed", "Tokens today / budget", "Cost (USD)", "Last active", ""]}>
          {(agents.data ?? []).map((a) => (
            <tr key={a.id} id={`agent-${a.id}`} className={focusAgent === a.id ? "bg-surface-2" : ""}>
              <td><div className="font-medium"><button className="text-left hover:text-violet" title="Show this agent's tasks" onClick={() => { setFocusAgent(a.id); history.replaceState(null, "", `/agents?agent=${a.id}`); }}>{a.name}</button></div><div className="max-w-72 truncate text-[11.5px] text-ink-3" title={a.description}>{a.description}</div></td>
              <td className="text-ink-2">{a.division}</td>
              <td>
                <select value={a.permission_level} onChange={(e) => patch(a.id, { permission_level: Number(e.target.value) })} title="Admin only; audited. Levels 4–5 always need human approval per action.">
                  {LEVELS.map((l, i) => <option key={i} value={i}>{l}</option>)}
                </select>
              </td>
              <td><StatusBadge status={a.status} /></td>
              <td className="num whitespace-nowrap">{a.running ? `${a.running} running · ` : ""}{a.queued} queued</td>
              <td className="num">{a.tasks_succeeded} / {a.tasks_blocked} / {a.tasks_failed}</td>
              <td className="num">{a.tokens_today.toLocaleString()} / {a.daily_token_budget.toLocaleString()}</td>
              <td className="num">{a.cost_total_usd.toFixed(3)}</td>
              <td className="text-ink-3">{ago(a.last_active_at)}</td>
              <td><Button variant={a.status === "active" ? "danger" : "ghost"} onClick={() => patch(a.id, { status: a.status === "active" ? "suspended" : "active" })}>{a.status === "active" ? "Suspend" : "Resume"}</Button></td>
            </tr>
          ))}
        </Table>
      </Card>

      <div className="mt-4 grid grid-cols-1 gap-4 xl:grid-cols-3">
        <Card title={focusAgent ? `Task queue · ${focusAgent}` : "Task queue"} className="xl:col-span-2" pad={false}
          action={focusAgent ? <button className="text-[12px] text-violet hover:underline" onClick={clearFocus}>show all agents</button> : undefined}>
          {tasks.data?.length ? (
            <Table head={["#", "Type", "Agent", "Status", "Depth", "Prio", "Tries", "Tokens", "Created", ""]}>
              {tasks.data.map((t) => (
                <Fragment key={t.id}>
                  <tr>
                    <td className="num text-ink-3">{t.id}</td><td className="font-mono text-[12px]">{t.type}</td><td className="text-ink-2">{t.agent_id}</td>
                    <td><StatusBadge status={t.status} /></td><td className="num">{t.depth}</td><td className="num">{t.priority}</td><td className="num">{t.attempts}/{t.max_attempts}</td>
                    <td className="num">{t.tokens_used}</td><td className="text-ink-3">{ago(t.created_at)}</td>
                    <td><button className="text-[12px] text-ink-3 hover:text-ink" onClick={() => setOpen(open === t.id ? null : t.id)}>{open === t.id ? "hide" : "details"}</button></td>
                  </tr>
                  {open === t.id && <tr><td colSpan={10}><TaskDetail id={t.id} /></td></tr>}
                </Fragment>
              ))}
            </Table>
          ) : <div className="p-4"><Empty title="Queue empty" /></div>}
        </Card>
        <div className="space-y-4">
          <Card title="Dispatch a task">
            <div className="space-y-2">
              <Field label="Task type"><select value={ttype} onChange={(e) => setTtype(e.target.value)}>
                <option value="">select…</option>{Object.entries(types.data ?? {}).map(([t, a]) => <option key={t} value={t}>{t} → {a}</option>)}
              </select></Field>
              <Field label="Payload (JSON)"><textarea rows={3} className="font-mono" value={payload} onChange={(e) => setPayload(e.target.value)} /></Field>
              <Button variant="primary" disabled={!ttype} onClick={submit}>Dispatch</Button>
            </div>
          </Card>
          <Card title="Live bus">
            <ul className="max-h-80 space-y-1 overflow-auto font-mono text-[11px]">
              {events.length ? events.map((e, i) => (
                <li key={i} className="text-ink-3"><span className="text-ink-2">{e.ts.slice(11, 19)}</span> {e.type} {e.task_type ?? e.action ?? ""} {e.agent ?? e.actor ?? ""} <span className="text-violet">{e.status ?? ""}</span></li>
              )) : <li className="text-ink-3">Waiting for agent activity…</li>}
            </ul>
          </Card>
        </div>
      </div>

      <Card title="Structured agent messages" className="mt-4" pad={false}>
        {msgs.data?.length ? (
          <Table head={["Agent", "Kind", "Summary", "Epistemic", "Confidence", "Impact (SEK)", "Risks", "When"]}>
            {msgs.data.map((m) => (
              <tr key={m.id}>
                <td className="text-ink-2">{m.agent_id}</td><td><StatusBadge status={m.kind === "result" ? "succeeded" : m.kind === "error" ? "failed" : "blocked"} /></td>
                <td className="max-w-xl text-[12.5px]">{m.summary.split("\n")[0]}</td><td><Epistemic kind={m.epistemic} /></td>
                <td className="num">{(m.confidence * 100).toFixed(0)}%</td><td className="num">{m.financial_impact_sek?.toFixed(0) ?? "—"}</td>
                <td className="max-w-xs text-[12px] text-warning">{m.risks.join("; ")}</td><td className="text-ink-3">{ago(m.created_at)}</td>
              </tr>
            ))}
          </Table>
        ) : <div className="p-4"><Empty title="No messages yet" /></div>}
      </Card>
    </>
  );
}

function TaskDetail({ id }: { id: number }) {
  const t = useApi<any>(`/api/tasks/${id}`, [id]);
  if (t.error) return <ErrorBanner error={t.error} />;
  if (!t.data) return null;
  const x = t.data;
  return (
    <>
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 pt-1 text-[12px]">
      <StatusBadge status={x.status} /><span className="font-mono text-ink-2">{x.type}</span>
      <Link className="text-violet underline underline-offset-2" href={`/agents?agent=${x.agent_id}`}>agent {x.agent_id}</Link>
      {x.run_id && <Link className="text-violet underline underline-offset-2" href={`/governance#runs/${x.run_id}`}>trace & replay · run #{x.run_id}</Link>}
      {x.parent_id && <Link className="text-violet underline underline-offset-2" href={`/agents?task=${x.parent_id}`}>parent task #{x.parent_id}</Link>}
      {x.children.map((c: number) => <Link key={c} className="text-violet underline underline-offset-2" href={`/agents?task=${c}`}>child #{c}</Link>)}
    </div>
    <div className="grid grid-cols-1 gap-3 py-2 md:grid-cols-2">
      <div><div className="mb-1 text-[11px] text-ink-3">payload</div><Json value={t.data.payload} /></div>
      <div><div className="mb-1 text-[11px] text-ink-3">{t.data.error ? "error" : "result"}{t.data.children.length ? ` · spawned ${t.data.children.join(", ")}` : ""}</div>
        {t.data.error ? <pre className="whitespace-pre-wrap rounded-md bg-bg p-3 font-mono text-[11.5px] text-[#f3a5a5]">{t.data.error}</pre> : <Json value={t.data.result} />}</div>
    </div>
    </>
  );
}
