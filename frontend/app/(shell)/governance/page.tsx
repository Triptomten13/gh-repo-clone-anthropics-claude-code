"use client";
/** DAEMON CONTROL PLANE — one place for the governance the backend enforces: policies & approvals, tool security,
 *  runs & replay, evaluation gates, audit & compliance, deployment & egress, budgets, roles. Every number and row
 *  comes from the API; governed changes show their "pending second approval" state instead of pretending to apply. */
import Link from "next/link";
import { useEffect, useState } from "react";
import { useDialog } from "@/components/dialog";
import { Button, Card, Empty, ErrorBanner, PageHeader, StatusBadge, Table } from "@/components/ui";
import { ago, api, API_URL, getToken } from "@/lib/api";
import { useApi } from "@/lib/hooks";

const TABS = [["policies", "Policies"], ["tools", "Tool security"], ["runs", "Runs & replay"], ["gates", "Evaluation gates"],
  ["audit", "Audit & compliance"], ["deployment", "Deployment & egress"], ["budgets", "Budgets"], ["roles", "Identity & roles"]] as const;
const CAT_STATUS: Record<string, string> = { AUTONOMOUS: "permitted", SUPERVISED: "review_required", APPROVAL_REQUIRED: "pending", RESTRICTED: "restricted", PROHIBITED: "blocked" };
const INV_STATUS: Record<string, string> = { ok: "succeeded", denied: "blocked", pending_approval: "pending", budget_exhausted: "blocked", not_configured: "missing_credentials", error: "failed", invalid: "rejected", blocked: "blocked" };

function Pending({ res }: { res: any }) {
  if (!res) return null;
  if (res.status === "pending_approval") {
    return <div role="status" className="mt-3 rounded-md border border-warning/40 bg-warning/10 px-3 py-2 text-[13px] text-warning">
      Filed as approval #{res.approval_id} ({res.category}). Another approver must approve it in the <Link className="underline" href="/approvals">Approval Center</Link>;
      then repeat the change with that approval. Nothing has changed yet.</div>;
  }
  return <div role="status" className="mt-3 rounded-md border border-good/40 bg-good/10 px-3 py-2 text-[13px] text-good">Applied.</div>;
}

export default function Governance() {
  const [tab, setTab] = useState<string>("policies");
  useEffect(() => { const h = window.location.hash.slice(1); if (TABS.some(([id]) => id === h)) setTab(h); }, []);
  const pick = (t: string) => { setTab(t); history.replaceState(null, "", `#${t}`); };
  return (
    <>
      <PageHeader kicker="Demonkoncernen · control plane" title="Governance & Audit">
        <span className="text-[12px] text-ink-3">enforced by the backend — the interface only shows and requests</span>
      </PageHeader>
      <div role="tablist" aria-label="Governance sections" className="mb-4 flex flex-wrap gap-1">
        {TABS.map(([id, name]) => <button key={id} role="tab" aria-selected={tab === id} onClick={() => pick(id)}
          className={`min-h-9 rounded-md border px-3 text-[12.5px] ${tab === id ? "border-violet bg-violet/10 text-ink" : "border-line text-ink-3 hover:text-ink-2"}`}>{name}</button>)}
      </div>
      {tab === "policies" ? <Policies /> : tab === "tools" ? <Tools /> : tab === "runs" ? <Runs /> : tab === "gates" ? <Gates /> :
        tab === "audit" ? <Audit /> : tab === "deployment" ? <Deployment /> : tab === "budgets" ? <Budgets /> : <Roles />}
    </>
  );
}

function Policies() {
  const p = useApi<any>("/api/policies");
  const [form, setForm] = useState({ key: "", action: "", category: 3, reason: "" });
  const [res, setRes] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);
  const submit = async () => { try { setRes(await api("/api/policies", { method: "POST", json: form })); setErr(null); p.reload(); } catch (e) { setErr((e as Error).message); } };
  const d = p.data;
  return (
    <div className="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1fr)_380px]">
      <div className="space-y-4">
        <ErrorBanner error={p.error} />
        <Card title={`Active rules · policy version ${d?.version ?? "…"}`} pad={false}>
          {d?.rules?.length ? <Table head={["Rule", "Action", "Category", "Conditions", "By"]} label="Policy rules">{d.rules.map((r: any) => (
            <tr key={r.id}><td className="font-mono text-[12px]">{r.key}@{r.version}</td><td className="font-mono text-[12px]">{r.action}</td>
              <td><StatusBadge status={CAT_STATUS[d.categories[r.category]] ?? "unverified"} /> <span className="text-[11px] text-ink-3">{d.categories[r.category]}</span></td>
              <td className="max-w-xs text-[11.5px] text-ink-3">{Object.keys(r.conditions || {}).length ? JSON.stringify(r.conditions) : "—"}</td><td className="text-ink-3">{r.created_by}</td></tr>))}</Table>
            : <div className="p-4"><Empty title="No configurable rules yet">The built-in floors below already apply to every action.</Empty></div>}
        </Card>
        <Card title="Mandatory floors (rules can raise, never lower)">
          <div className="grid grid-cols-1 gap-x-6 gap-y-1 text-[12.5px] sm:grid-cols-2">
            {d && Object.entries(d.mandatory.floors).map(([k, v]: any) => <div key={k} className="flex justify-between gap-2"><span className="font-mono text-ink-2">{k}</span><span className="text-ink-3">{v}</span></div>)}
          </div>
          {d && <p className="mt-3 text-[12px] text-ink-3">Never executable: <span className="font-mono">{d.mandatory.prohibited.join(", ")}</span>. Agents may never perform: <span className="font-mono">{d.mandatory.agent_prohibited.join(", ")}</span>.</p>}
        </Card>
      </div>
      <Card title="Propose a rule (needs a second approver)">
        <div className="space-y-2">
          <label className="block text-[12px] text-ink-3">Key<input className="mt-1 w-full" value={form.key} onChange={(e) => setForm({ ...form, key: e.target.value })} placeholder="email.restricted" /></label>
          <label className="block text-[12px] text-ink-3">Action (exact or pattern with *)<input className="mt-1 w-full" value={form.action} onChange={(e) => setForm({ ...form, action: e.target.value })} placeholder="tool:email.send.EXECUTE" /></label>
          <label className="block text-[12px] text-ink-3">Category<select className="mt-1 w-full" value={form.category} onChange={(e) => setForm({ ...form, category: Number(e.target.value) })}>
            {d && Object.entries(d.categories).map(([n, name]: any) => <option key={n} value={n}>{n} · {name}</option>)}</select></label>
          <label className="block text-[12px] text-ink-3">Reason<input className="mt-1 w-full" value={form.reason} onChange={(e) => setForm({ ...form, reason: e.target.value })} /></label>
          <Button variant="primary" disabled={form.key.length < 3 || !form.action} onClick={submit}>Propose</Button>
          <ErrorBanner error={err} /><Pending res={res} />
        </div>
      </Card>
    </div>
  );
}

function Tools() {
  const t = useApi<any>("/api/tools");
  const g = useApi<any[]>("/api/tools/grants");
  const inv = useApi<any[]>("/api/tools/invocations?limit=60");
  const dlg = useDialog();
  const revoke = async (id: number) => { if (await dlg.confirm({ title: `Revoke grant #${id}?`, message: "Access ends immediately.", confirmLabel: "Revoke", danger: true })) { await api(`/api/tools/grants/${id}`, { method: "DELETE" }); g.reload(); } };
  return (
    <div className="space-y-4">
      <ErrorBanner error={t.error || g.error} />
      <Card title="Tools (deny by default — an agent needs an explicit grant)" pad={false}>
        <Table head={["Tool", "Operation", "Leaves the deployment", "Output", "Credential"]} label="Tools">{(t.data?.tools ?? []).map((x: any) => (
          <tr key={x.name}><td className="font-mono text-[12px]">{x.name}</td><td>{x.operation}</td><td>{x.external ? "yes" : "no"}</td><td>{x.output_class}</td><td className="text-ink-3">{x.credential ?? "—"}</td></tr>))}</Table>
      </Card>
      <Card title="Grants" pad={false}>
        {g.data?.length ? <Table head={["Subject", "Tool", "Ops", "Limit/day", "Credential scope", "State", ""]} label="Tool grants">{g.data.map((x) => (
          <tr key={x.id}><td>{x.subject_kind}:<span className="font-mono">{x.subject_id}</span></td><td className="font-mono text-[12px]">{x.tool}</td><td>{x.operations.join(" ")}</td>
            <td className="num">{x.max_calls_per_day ?? "—"}</td><td className="text-ink-3">{x.credential_scope || "—"}</td><td><StatusBadge status={x.enabled ? "active" : "revoked"} /></td>
            <td>{x.enabled && <Button variant="danger" onClick={() => revoke(x.id)}>Revoke</Button>}</td></tr>))}</Table> : <div className="p-4"><Empty title="No grants" /></div>}
      </Card>
      <Card title="Recent invocations (every request is recorded — allowed or not)" pad={false}>
        {inv.data?.length ? <Table head={["When", "Tool", "Who", "Decision", "Reason", "ms"]} label="Tool invocations">{inv.data.map((x) => (
          <tr key={x.id}><td className="text-ink-3">{ago(x.created_at)}</td><td className="font-mono text-[12px]">{x.tool}.{x.operation}</td><td>{x.agent_id ? `agent ${x.agent_id}` : x.user_email}</td>
            <td><StatusBadge status={INV_STATUS[x.status] ?? x.status} /></td><td className="max-w-sm text-[11.5px] text-ink-3">{x.reason}</td><td className="num">{x.latency_ms}</td></tr>))}</Table>
          : <div className="p-4"><Empty title="No tool calls yet" /></div>}
      </Card>
    </div>
  );
}

function Runs() {
  const runs = useApi<any[]>("/api/runs?limit=80");
  const [sel, setSel] = useState<number | null>(null);
  const rep = useApi<any>(sel ? `/api/runs/${sel}/replay` : null, [sel]);
  return (
    <div className="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
      <Card title="Executions" pad={false}>
        <ErrorBanner error={runs.error} />
        {runs.data?.length ? <Table head={["Run", "Kind", "Workflow / agent", "Status", "Started", "Cost"]} label="Runs">{runs.data.map((r) => (
          <tr key={r.id} className={sel === r.id ? "bg-surface-2" : ""}><td><button className="font-mono text-violet hover:underline" onClick={() => setSel(r.id)}>#{r.id}</button></td>
            <td>{r.kind}</td><td className="text-[12px]">{r.workflow}{r.agent_id && <span className="text-ink-3"> · {r.agent_id}</span>}</td><td><StatusBadge status={r.status} /></td>
            <td className="text-ink-3">{ago(r.started_at)}</td><td className="num">${(r.cost_usd ?? 0).toFixed(4)}</td></tr>))}</Table>
          : <div className="p-4"><Empty title="No runs yet">Tasks and Ask requests create runs.</Empty></div>}
      </Card>
      <Card title={sel ? `Replay · run #${sel}` : "Replay"}>
        {!sel ? <Empty title="Select a run" /> : rep.data ? (<>
          <p className="mb-3 text-[12px] text-ink-3">{rep.data.replay_kind}. Policy version {rep.data.run.policy_version || "—"}.</p>
          <ol className="space-y-2">{rep.data.events.map((e: any) => (
            <li key={e.seq} className="rounded-md border border-line bg-bg/50 p-2 text-[12.5px]">
              <div className="flex flex-wrap items-center gap-2"><span className="num text-ink-3">{e.seq}</span><span className="font-mono text-cyan">{e.type}</span><span>{e.name}</span>
                {e.duration_ms != null && <span className="num ml-auto text-[11px] text-ink-3">{e.duration_ms} ms</span>}</div>
              <pre className="mt-1 max-h-40 overflow-auto whitespace-pre-wrap break-all font-mono text-[11px] text-ink-3">{JSON.stringify(e.data, null, 1)}</pre></li>))}</ol>
          {rep.data.model_calls.length > 0 && <p className="mt-3 text-[12px] text-ink-3">{rep.data.model_calls.length} model attempt(s) · {rep.data.tool_invocations.length} tool call(s) · {rep.data.approvals.length} approval(s) linked.</p>}
        </>) : <ErrorBanner error={rep.error} />}
      </Card>
    </div>
  );
}

function Gates() {
  const g = useApi<any>("/api/gates");
  const [res, setRes] = useState<any>(null);
  const check = async () => setRes(await api("/api/gates/check", { method: "POST", json: { target_kind: "prompt", target_ref: "manual-check" } }));
  return (
    <div className="space-y-4">
      <ErrorBanner error={g.error} />
      <Card title="Release gates (a failed mandatory gate blocks the release)" action={<Button onClick={async () => { await check(); g.reload(); }}>Run prompt gates now</Button>} pad={false}>
        <Table head={["Applies to", "Suite", "Minimum", "Mandatory"]} label="Release gates">{(g.data?.gates ?? []).map((x: any) => (
          <tr key={x.id}><td>{x.target_kind}</td><td className="font-mono text-[12px]">{x.suite}</td><td className="num">{x.min_score}</td><td>{x.mandatory ? "yes — blocks" : "advisory"}</td></tr>))}</Table>
        {res && <div className="p-4 text-[13px]"><StatusBadge status={res.passed ? "succeeded" : "failed"} /> gate run #{res.gate_run.id}</div>}
      </Card>
      <Card title="History (regressions stay visible)" pad={false}>
        {g.data?.runs?.length ? <Table head={["When", "Target", "Result", "Scores", "Blocking"]} label="Gate runs">{g.data.runs.map((r: any) => (
          <tr key={r.id}><td className="text-ink-3">{ago(r.created_at)}</td><td className="font-mono text-[12px]">{r.target_kind}:{r.target_ref}</td><td><StatusBadge status={r.passed ? "succeeded" : "failed"} /></td>
            <td className="text-[11.5px]">{Object.entries(r.results).map(([k, v]: any) => `${k} ${v.score ?? "—"}`).join(" · ")}</td><td className="text-[11.5px] text-critical">{r.blocking.join("; ")}</td></tr>))}</Table>
          : <div className="p-4"><Empty title="No gate runs yet">Activating a prompt or a model runs its gates.</Empty></div>}
      </Card>
    </div>
  );
}

function Audit() {
  const [v, setV] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);
  const [f, setF] = useState({ actor: "", action: "" });
  const recs = useApi<any[]>(`/api/audit/records?limit=100${f.actor ? `&actor=${encodeURIComponent(f.actor)}` : ""}${f.action ? `&action=${encodeURIComponent(f.action)}` : ""}`, [f.actor, f.action]);
  const verify = async () => { try { setV(await api("/api/audit/verify")); setErr(null); } catch (e) { setErr((e as Error).message); } };
  const download = async (fmt: string) => {
    try {
      const r = await fetch(`${API_URL}/api/audit/export?fmt=${fmt}`, { headers: { Authorization: `Bearer ${getToken()}` } });
      if (!r.ok) throw new Error((await r.json().catch(() => ({ detail: r.statusText }))).detail);
      const url = URL.createObjectURL(await r.blob());
      const a = document.createElement("a"); a.href = url; a.download = `demonkoncernen-audit.${fmt}`; a.click(); URL.revokeObjectURL(url);
    } catch (e) { setErr((e as Error).message); }
  };
  return (
    <div className="space-y-4">
      <Card title="Integrity (keyed hash chain)" action={<span className="flex flex-wrap gap-2"><Button onClick={verify}>Verify now</Button>
        <Button onClick={() => download("zip")}>Export signed ZIP</Button><Button onClick={() => download("csv")}>CSV</Button></span>}>
        <ErrorBanner error={err} />
        {v ? <div className="text-[13px]"><StatusBadge status={v.ok ? "succeeded" : "failed"} /> {v.ok ? `${v.checked} records verified (seq ${v.first_seq}–${v.last_seq}); head ${v.head_hash?.slice(0, 16)}…` : `${v.reason} (at seq ${v.failed_at_seq})`}
          <p className="mt-2 text-[12px] text-ink-3">{v.limitations ?? "Detects edits, deletions, re-ordering and truncation by anyone without the audit key."}</p></div>
          : <p className="text-[13px] text-ink-3">Verification walks every record from the retention anchor and reports the first one that does not match its seal.</p>}
      </Card>
      <Card title="Records" pad={false}>
        <div className="flex flex-wrap gap-2 p-3">
          <input aria-label="filter by actor" placeholder="actor" value={f.actor} onChange={(e) => setF({ ...f, actor: e.target.value })} />
          <input aria-label="filter by action" placeholder="action, e.g. tool.* or policy.*" value={f.action} onChange={(e) => setF({ ...f, action: e.target.value })} />
        </div>
        <ErrorBanner error={recs.error} />
        {recs.data?.length ? <Table head={["Seq", "When", "Actor", "Action", "Target", "Hash"]} label="Audit records">{recs.data.map((r) => (
          <tr key={r.id}><td className="num">{r.seq ?? "…"}</td><td className="text-ink-3">{ago(r.created_at)}</td><td>{r.actor}</td><td className="font-mono text-[12px]">{r.action}</td>
            <td className="max-w-xs truncate text-[12px]">{r.target}</td><td className="font-mono text-[11px] text-ink-3">{r.hash?.slice(0, 10)}</td></tr>))}</Table>
          : <div className="p-4"><Empty title="No matching records" /></div>}
      </Card>
    </div>
  );
}

function Deployment() {
  const d = useApi<any>("/api/deployment");
  const [probe, setProbe] = useState<any>(null);
  const [res, setRes] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);
  const dlg = useDialog();
  const setProfile = async (profile: string) => {
    if (!(await dlg.confirm({ title: `Switch to ${profile}?`, message: profile === "AIR_GAPPED" ? "Offline mode is forced on and every outbound connection outside loopback, private networks and the allow-list is refused." : "Loosening egress needs a second approver.", confirmLabel: "Switch" }))) return;
    try { setRes(await api("/api/deployment", { method: "POST", json: { profile, egress_allowlist: d.data?.deployment?.egress_allowlist ?? [] } })); d.reload(); } catch (e) { setErr((e as Error).message); }
  };
  const e = d.data?.egress;
  return (
    <div className="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
      <Card title={`Profile · ${d.data?.deployment?.profile ?? "…"}`}>
        <ErrorBanner error={d.error || err} />
        <ul className="space-y-1.5 text-[13px]">{d.data && Object.entries(d.data.profiles).map(([k, v]: any) => (
          <li key={k} className="flex flex-wrap items-center gap-2"><Button variant={d.data.deployment.profile === k ? "primary" : "ghost"} onClick={() => setProfile(k)} disabled={d.data.deployment.profile === k}>{k}</Button><span className="text-ink-3">{v}</span></li>))}</ul>
        <Pending res={res} />
      </Card>
      <Card title="Outbound connections" action={<Button onClick={async () => setProbe(await api("/api/deployment/egress/verify"))}>Self-test</Button>}>
        {e && <div className="text-[13px]"><StatusBadge status={e.enforcing ? "restricted" : "permitted"} /> {e.enforcing ? "restricted" : "not restricted (online)"} · allowed {e.counts.allowed} · refused {e.counts.denied}
          <p className="mt-1 text-[12px] text-ink-3">{e.scope}</p></div>}
        {probe && <p className="mt-2 text-[13px]"><StatusBadge status={probe.probe.blocked ? "blocked" : "permitted"} /> {probe.probe.result}</p>}
        {e?.recent?.length > 0 && <ul className="mt-3 max-h-48 space-y-1 overflow-auto text-[11.5px]">{e.recent.slice().reverse().map((a: any, i: number) => <li key={i} className={a.allowed ? "text-ink-3" : "text-critical"}>{a.allowed ? "✓" : "✗"} {a.host}:{a.port} — {a.reason}</li>)}</ul>}
      </Card>
      <Card title="What works without the internet" className="xl:col-span-2">
        {d.data && <div className="grid grid-cols-1 gap-4 text-[13px] sm:grid-cols-2">{Object.entries(d.data.features).map(([k, v]: any) => (
          <div key={k}><div className="mb-1 font-mono text-[11px] uppercase tracking-[0.14em] text-ink-3">{k}</div><ul className="list-disc space-y-0.5 pl-5">{v.map((x: string) => <li key={x}>{x}</li>)}</ul></div>))}</div>}
      </Card>
    </div>
  );
}

function Budgets() {
  const b = useApi<any[]>("/api/budgets");
  const [form, setForm] = useState({ scope_kind: "agent", scope_id: "*", metric: "model_calls", period: "day", limit: 100 });
  const [res, setRes] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);
  const submit = async () => { try { setRes(await api("/api/budgets", { method: "POST", json: form })); setErr(null); b.reload(); } catch (e) { setErr((e as Error).message); } };
  return (
    <div className="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1fr)_360px]">
      <Card title="Hard limits (checked before a call runs — never bypassed)" pad={false}>
        <ErrorBanner error={b.error} />
        {b.data?.length ? <Table head={["Scope", "Metric", "Limit", "Used today", "State"]} label="Budgets">{b.data.map((x) => (
          <tr key={x.id}><td>{x.scope_kind}:<span className="font-mono">{x.scope_id}</span></td><td>{x.metric}/{x.period}</td><td className="num">{x.limit}</td>
            <td className="num">{x.used_today ?? "—"}</td><td><StatusBadge status={x.enabled ? "active" : "disabled"} /></td></tr>))}</Table>
          : <div className="p-4"><Empty title="No budget rules">Global daily/monthly USD limits and per-agent token budgets (DAEMON CORE) still apply.</Empty></div>}
      </Card>
      <Card title="Propose a limit (second approver)">
        <div className="space-y-2 text-[12px] text-ink-3">
          <label className="block">Scope<select className="mt-1 w-full" value={form.scope_kind} onChange={(e) => setForm({ ...form, scope_kind: e.target.value })}>{["agent", "workflow", "user", "global"].map((s) => <option key={s}>{s}</option>)}</select></label>
          <label className="block">Scope id (* = all)<input className="mt-1 w-full" value={form.scope_id} onChange={(e) => setForm({ ...form, scope_id: e.target.value })} /></label>
          <label className="block">Metric<select className="mt-1 w-full" value={form.metric} onChange={(e) => setForm({ ...form, metric: e.target.value })}>{["model_calls", "tokens", "usd", "tool_calls"].map((s) => <option key={s}>{s}</option>)}</select></label>
          <label className="block">Per<select className="mt-1 w-full" value={form.period} onChange={(e) => setForm({ ...form, period: e.target.value })}><option>day</option><option>month</option></select></label>
          <label className="block">Limit<input type="number" min={0} className="mt-1 w-full" value={form.limit} onChange={(e) => setForm({ ...form, limit: Number(e.target.value) })} /></label>
          <Button variant="primary" onClick={submit} disabled={!(form.limit > 0)}>Propose</Button>
          <ErrorBanner error={err} /><Pending res={res} />
        </div>
      </Card>
    </div>
  );
}

function Roles() {
  const r = useApi<any>("/api/rbac/roles");
  const me = useApi<any>("/api/auth/me");
  const perms = r.data ? Object.keys(r.data.permissions) : [];
  return (
    <Card title={`Roles and permissions · you are ${me.data?.role ?? "…"}`} pad={false}>
      <ErrorBanner error={r.error} />
      {r.data && <>
        <p className="px-4 pt-3 text-[12px] text-ink-3">{r.data.note}. Manage people in <Link className="text-violet hover:underline" href="/settings">Systems & Integrations</Link>.</p>
        <Table head={["Permission", ...Object.keys(r.data.roles)]} label="Role permission matrix">{perms.map((p) => (
          <tr key={p}><td><span className="font-mono text-[12px]">{p}</span><div className="text-[11px] text-ink-3">{r.data.permissions[p]}</div></td>
            {Object.entries(r.data.roles).map(([role, list]: any) => <td key={role} className="text-center">{list.includes(p) ? <span aria-label={`${role} has ${p}`}>●</span> : <span className="text-ink-3" aria-label={`${role} lacks ${p}`}>·</span>}</td>)}</tr>))}</Table>
      </>}
    </Card>
  );
}
