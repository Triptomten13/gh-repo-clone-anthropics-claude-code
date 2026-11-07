"use client";
/** Model Hunter, Model Championship, Devil's Advocate and Account Vault — every number from the backend, every action
 *  governed there (approvals, permissions, budgets). This page only shows and asks. */
import Link from "next/link";
import { Fragment, useEffect, useState } from "react";
import { Button, Card, Empty, ErrorBanner, Field, PageHeader, Stat, StatusBadge, Table } from "@/components/ui";
import { ago, api } from "@/lib/api";
import { useApi, useMe } from "@/lib/hooks";

const TABS = [["hunter", "Model Hunter"], ["championship", "Championship"], ["advocate", "Devil's Advocate"], ["vault", "Account Vault"]] as const;
const gb = (b: number) => `${(b / 1e9).toFixed(b >= 1e10 ? 0 : 2)} GB`;
const C_STATUS: Record<string, string> = { shortlisted: "review_required", screened_out: "rejected", pending_approval: "pending", approved: "approved",
  acquiring: "running", installed: "installed", rejected: "rejected", failed: "failed" };
const V_STATUS: Record<string, string> = { sound: "succeeded", concerns: "review_required", block: "blocked" };

export default function Autonomy() {
  const [tab, setTab] = useState<string>("hunter");
  useEffect(() => { const h = window.location.hash.slice(1); if (TABS.some(([id]) => id === h)) setTab(h); }, []);
  const pick = (t: string) => { setTab(t); history.replaceState(null, "", `#${t}`); };
  return (
    <>
      <PageHeader kicker="G-SUS · laboratory" title="Model Hunter, Critic & Vault">
        <span className="text-[12px] text-ink-3">measured on this hardware · challenged · secrets never reach a model</span>
      </PageHeader>
      <div role="tablist" aria-label="Sections" className="mb-4 flex flex-wrap gap-1">
        {TABS.map(([id, name]) => <button key={id} role="tab" aria-selected={tab === id} onClick={() => pick(id)}
          className={`min-h-9 rounded-md border px-3 text-[12.5px] ${tab === id ? "border-violet bg-violet/10 text-ink" : "border-line text-ink-3 hover:text-ink-2"}`}>{name}</button>)}
      </div>
      {tab === "hunter" ? <Hunter /> : tab === "championship" ? <Championship /> : tab === "advocate" ? <Advocate /> : <Vault />}
    </>
  );
}

// ------------------------------------------------------------------ Model Hunter
function Hunter() {
  const b = useApi<any>("/api/hunter");
  const me = useMe();
  const [task, setTask] = useState("general");
  const [show, setShow] = useState("shortlisted");
  const [busy, setBusy] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const act = async (key: string, f: () => Promise<any>, ok: (r: any) => string) => {
    setBusy(key); setErr(null); setMsg(null);
    try { setMsg(ok(await f())); b.reload(); } catch (e) { setErr((e as Error).message); } finally { setBusy(null); }
  };
  const d = b.data;
  const rows = (d?.candidates ?? []).filter((c: any) => show === "all" || c.status === show || (show === "shortlisted" && ["pending_approval", "approved", "acquiring", "installed", "failed"].includes(c.status)));
  return (
    <div className="space-y-4">
      <ErrorBanner error={err || b.error} />
      {msg && <p role="status" className="text-[13px] text-good">{msg}</p>}
      <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
        <Stat label="Shortlisted" value={d?.counts?.shortlisted ?? "…"} sub="passed screening" />
        <Stat label="Screened out" value={d?.counts?.screened_out ?? "…"} sub="before any download" />
        <Stat label="Waiting for approval" value={d?.counts?.pending_approval ?? "…"} />
        <Stat label="Installed by the Hunter" value={d?.counts?.installed ?? "…"} />
        <Stat label="This machine" value={d ? `${d.hardware.ram_gb} GB RAM` : "…"} sub={d ? `${d.hardware.disk_free_gb} GB disk free · budget ${d.storage_budget_gb} GB/model` : ""} />
      </div>
      <Card title="Search Hugging Face (official API — downloads nothing)">
        <div className="flex flex-wrap items-end gap-2">
          <Field label="Looking for"><select value={task} onChange={(e) => setTask(e.target.value)}>
            {Object.entries(d?.tasks ?? { general: "" }).map(([k, v]) => <option key={k} value={k}>{k} — {String(v)}</option>)}</select></Field>
          <Button variant="primary" busy={busy === "discover"} onClick={() => act("discover", () => api("/api/hunter/discover", { method: "POST", json: { task, limit: 15 } }),
            (r) => `${r.task}: ${r.searched} searched · ${r.new} new · ${r.unchanged} unchanged since last scan · ${r.shortlisted ?? 0} shortlisted · ${r.screened_out ?? 0} screened out`)}>Search</Button>
        </div>
        <p className="mt-2 text-[12px] text-ink-3">Screening happens before anything is downloaded: single-file GGUF only (no pickle weights, no repository code), a declared chat or embedding task, a stated licence, not gated, not safety-stripped, within RAM and the storage budget. Downloads and likes are shown, never used as evidence — the Championship decides.</p>
      </Card>
      <Card title="Candidates" pad={false} action={<select aria-label="Show candidates" value={show} onChange={(e) => setShow(e.target.value)}>
        <option value="shortlisted">shortlisted & in progress</option><option value="screened_out">screened out</option><option value="all">all</option></select>}>
        {rows.length ? <Table head={["Model", "For", "Size", "Licence", "State", "Why", ""]} label="Model candidates">{rows.map((c: any) => (
          <tr key={c.id} className="align-top">
            <td className="min-w-[14rem]"><a className="text-violet underline underline-offset-2" href={`https://huggingface.co/${c.repo}`} target="_blank" rel="noopener noreferrer">{c.repo}</a>
              <div className="font-mono text-[11px] text-ink-3">{c.quantization}{c.parameters_b ? ` · ${c.parameters_b} B params` : ""} · {c.downloads.toLocaleString()} downloads</div></td>
            <td className="text-ink-2">{c.task}</td><td className="num">{gb(c.size_bytes)}</td><td className="text-[12px]">{c.license || "—"}</td>
            <td><StatusBadge status={C_STATUS[c.status] ?? c.status} /> <span className="text-[11px] text-ink-3">{c.status.replace("_", " ")}</span></td>
            <td className="max-w-sm text-[12px] text-ink-3">{(c.reasons ?? []).join("; ")}
              {c.critique_id && <div><Link className="text-violet underline underline-offset-2" href="/autonomy#advocate">critique #{c.critique_id}</Link></div>}
              {c.approval_id && <div><Link className="text-violet underline underline-offset-2" href={`/approvals?id=${c.approval_id}`}>approval #{c.approval_id}</Link></div>}</td>
            <td>{c.status === "shortlisted" && <Button busy={busy === `r${c.id}`} onClick={() => act(`r${c.id}`, () => api(`/api/hunter/candidates/${c.id}/request`, { method: "POST" }),
                (r) => `${r.repo}: ${r.status === "pending_approval" ? `waiting for approval #${r.approval_id}` : r.status}`)}>Request download</Button>}
              {["pending_approval", "approved"].includes(c.status) && me?.role === "admin" && <Button busy={busy === `a${c.id}`} onClick={() => act(`a${c.id}`,
                () => api(`/api/hunter/candidates/${c.id}/acquire`, { method: "POST" }), () => "Downloading — the checksum and licence are verified before it is installed.")}>Download</Button>}</td>
          </tr>))}</Table> : <div className="p-4"><Empty title={b.loading ? "Loading…" : "No candidates here"}>Search for a task above.</Empty></div>}
      </Card>
    </div>
  );
}

// ------------------------------------------------------------------ Championship
function Championship() {
  const l = useApi<any>("/api/championships");
  const [sel, setSel] = useState<number | null>(null);
  const d = useApi<any>(sel ? `/api/championships/${sel}` : null, [sel]);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (!sel && l.data?.championships?.length) setSel(l.data.championships[0].id); }, [l.data, sel]);
  useEffect(() => { if (!l.data?.running) return; const t = setInterval(() => { l.reload(); d.reload(); }, 10000); return () => clearInterval(t); }, [l.data?.running]); // eslint-disable-line react-hooks/exhaustive-deps
  const start = async () => { setBusy(true); setErr(null); try { await api("/api/championships", { method: "POST", json: {} }); l.reload(); } catch (e) { setErr((e as Error).message); } finally { setBusy(false); } };
  const x = d.data;
  return (
    <div className="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,360px)_minmax(0,1fr)]">
      <div className="space-y-4">
        <Card title="Same tasks · same hardware · same run">
          <ErrorBanner error={err || l.error} />
          {l.data && <>
            <p className="text-[12.5px] text-ink-2">{l.data.hardware.cpu} · {l.data.hardware.cores} cores · {l.data.hardware.ram_gb} GB{l.data.hardware.gpus?.length ? ` · ${l.data.hardware.gpus.join(", ")}` : " · no GPU"}</p>
            <p className="mt-1 text-[12px] text-ink-3">{l.data.suites.daemon} + creative {l.data.suites.creative}; {l.data.suites.call}.</p>
            <p className="mt-2 text-[12px] text-ink-3">Contenders: {l.data.contenders.map((c: any) => `${c.key} (${c.size_gb} GB)`).join(", ") || "none installed"}</p>
            <div className="mt-3"><Button variant="primary" busy={busy} disabled={l.data.running || !l.data.contenders.length} onClick={start}>{l.data.running ? "Running…" : "Start a championship"}</Button></div>
            <p className="mt-2 text-[11.5px] text-ink-3">Local models share this CPU, so one championship runs at a time; smaller models go first and a time budget stops it before it runs for hours.</p>
          </>}
        </Card>
        <Card title="Championships" pad={false}>
          {l.data?.championships?.length ? <ul className="divide-y divide-line">{l.data.championships.map((c: any) => (
            <li key={c.id}><button onClick={() => setSel(c.id)} className={`w-full px-4 py-2.5 text-left hover:bg-surface-2 ${sel === c.id ? "bg-surface-2" : ""}`}>
              <div className="flex items-center gap-2 text-[12px]"><span className="font-mono text-violet">#{c.id}</span><StatusBadge status={c.status === "completed" ? "succeeded" : c.status} />
                <span className="text-ink-3">{(c.participants ?? []).length} contenders · {ago(c.started_at)}</span></div>
              <div className="mt-0.5 text-[12.5px] text-ink-2">{c.deltas?.verdict ?? c.summary}</div></button></li>))}</ul>
            : <div className="p-4"><Empty title="No championship yet">The first one becomes the baseline for this hardware.</Empty></div>}
        </Card>
      </div>
      <div className="min-w-0 space-y-4">
        {x ? <>
          <Card title={`Championship #${x.id}`} action={<StatusBadge status={x.status === "completed" ? "succeeded" : x.status} />}>
            <p className="text-[13px] text-ink-2">{x.summary || x.error || "Running…"}</p>
            {x.deltas?.changes?.length > 0 && <ul className="mt-3 space-y-1 text-[12.5px]">{x.deltas.changes.map((c: any) => (
              <li key={c.category}><span className={c.kind === "regressed" ? "text-[#f08a8a]" : "text-good"}>{c.kind}</span> · {c.category}: {c.before.model} {fmtv(c.before.value)} → {c.after.model} {fmtv(c.after.value)}
                {c.new_leader && <span className="text-ink-3"> (new leader)</span>}</li>))}</ul>}
            {x.deltas && !x.deltas.changes?.length && <p className="mt-2 text-[12.5px] text-ink-3">{x.deltas.verdict}</p>}
          </Card>
          <Card title="Standings (best first; latency and cost: lower is better)" pad={false}>
            {x.standings && Object.keys(x.standings).length ? <Table head={["Category", "1st", "2nd", "3rd"]} label="Standings">{Object.entries(x.standings).map(([cat, rows]: any) => (
              <tr key={cat}><td className="text-[12.5px]">{cat}</td>{[0, 1, 2].map((i) => <td key={i} className="text-[12px]">{rows[i] ? <><span className="font-mono">{rows[i].model}</span> <span className="num text-ink-3">{fmtv(rows[i].value)}</span></> : "—"}</td>)}</tr>))}</Table>
              : <div className="p-4 text-[13px] text-ink-3">{x.status === "running" ? "Measuring…" : "No standings."}</div>}
          </Card>
          <Card title="Measured per contender" pad={false}>
            <Table head={["Model", "Accuracy", "Tokens/s", "p50 latency", "Cost/success", "Songwriting", "Time"]} label="Results">{Object.entries(x.results ?? {}).map(([m, r]: any) => (
              <tr key={m}><td className="font-mono text-[12px]">{m}</td>{r.error ? <td colSpan={6} className="text-[12px] text-warning">{r.error}</td> : <>
                <td className="num">{fmtv(r.accuracy)}</td><td className="num">{fmtv(r.tokens_per_s)}</td><td className="num">{r.latency_p50_ms ? `${(r.latency_p50_ms / 1000).toFixed(1)} s` : "—"}</td>
                <td className="num">{r.cost_per_success_usd != null ? `$${r.cost_per_success_usd}` : "—"}</td><td className="num">{fmtv(r.creative?.songwriting)}</td><td className="num">{r.seconds} s</td></>}</tr>))}</Table>
          </Card>
        </> : <Card><Empty title={l.loading ? "Loading…" : "Select a championship"} /></Card>}
      </div>
    </div>
  );
}
const fmtv = (v: any) => (v == null ? "—" : typeof v === "number" ? (Math.abs(v) < 1 && v !== 0 ? v.toFixed(3) : v.toFixed(v % 1 ? 2 : 0)) : String(v));

// ------------------------------------------------------------------ Devil's Advocate
const EXAMPLE = JSON.stringify({ kind: "model_selection", ref: "example", summary: "use the 8B model for product names", objective: "better names",
  evidence: [], alternatives: [], verification: "", model: "local:qwen3-8b", measured: false }, null, 1);

function Advocate() {
  const b = useApi<any>("/api/advocate");
  const [open, setOpen] = useState<number | null>(null);
  const [text, setText] = useState(EXAMPLE);
  const [useModel, setUseModel] = useState(false);
  const [mode, setMode] = useState("DEVILS_ADVOCATE");
  const [res, setRes] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const review = async () => {
    setBusy(true); setErr(null);
    try { setRes(await api("/api/advocate/review", { method: "POST", json: { decision: JSON.parse(text), mode, use_model: useModel } })); b.reload(); }
    catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  };
  const cal = b.data?.calibration, agr = b.data?.agreement;
  return (
    <div className="space-y-4">
      <ErrorBanner error={b.error} />
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label="Calibration" value={cal ? `${cal.correct}/${cal.total}` : "…"} sub="known cases judged correctly" />
        <Stat label="Bad decisions flagged" value={cal ? `${cal.bad_flagged}/${cal.bad_total}` : "…"} />
        <Stat label="Good decisions passed" value={cal ? `${cal.good_passed}/${cal.good_total}` : "…"} sub="it says so when a decision is sound" />
        <Stat label="Agreement rate" value={agr?.sound_share != null ? `${Math.round(agr.sound_share * 100)} %` : "—"} sub={agr ? `${agr.reviews} recent reviews` : ""} />
      </div>
      {agr?.warning && <p role="status" className="rounded-md border border-warning/40 bg-warning/10 px-3 py-2 text-[13px] text-warning">{agr.warning}</p>}
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,420px)]">
        <Card title="Reviews" pad={false}>
          {b.data?.critiques?.length ? <ul className="divide-y divide-line">{b.data.critiques.map((c: any) => (
            <li key={c.id} className="px-4 py-3">
              <button className="flex w-full flex-wrap items-center gap-2 text-left" aria-expanded={open === c.id} onClick={() => setOpen(open === c.id ? null : c.id)}>
                <span className="font-mono text-[12px] text-violet">#{c.id}</span><StatusBadge status={V_STATUS[c.verdict]} /><span className="text-[12px] text-ink-3">{c.verdict} · {c.subject_kind} · {c.subject_ref} · {c.reviewer}</span>
                <span className="ml-auto text-[11px] text-ink-3">{ago(c.created_at)}</span></button>
              <p className="mt-1 text-[13px] text-ink-2">{c.summary}</p>
              {open === c.id && <div className="mt-2 space-y-2">
                {c.findings.map((f: any, i: number) => <div key={i} className="rounded-md border border-line bg-bg/50 p-2 text-[12.5px]">
                  <div><span className={f.blocking ? "text-[#f08a8a]" : f.severity === "important" ? "text-warning" : "text-ink-3"}>{f.blocking ? "blocking" : f.severity}</span> · {f.weakness}
                    <span className="text-ink-3"> · confidence {Math.round(f.confidence * 100)} % · {f.source}</span></div>
                  <div className="text-ink-3">Evidence: {f.evidence}</div><div className="text-ink-3">Consequence: {f.consequence}</div>
                  <div className="text-ink-2">Alternative: {f.alternative} — {f.recommendation}</div></div>)}
                {!!c.checks?.length && <p className="text-[11.5px] text-ink-3">Checked: {c.checks.join(" · ")}</p>}
                {c.response && <p className="text-[12px] text-ink-2">Response: {c.response}</p>}
              </div>}
            </li>))}</ul> : <div className="p-4"><Empty title={b.loading ? "Loading…" : "No reviews yet"}>Acquisitions, account requests and G-SUS plans are reviewed automatically.</Empty></div>}
        </Card>
        <div className="space-y-4">
          <Card title="Challenge a decision">
            <ErrorBanner error={err} />
            <Field label="Mode"><select value={mode} onChange={(e) => setMode(e.target.value)}>{(b.data?.modes ?? ["DEVILS_ADVOCATE"]).map((m: string) => <option key={m}>{m}</option>)}</select></Field>
            <Field label="Decision record (JSON: kind, summary, objective, evidence, alternatives, assumptions, risks, verification …)">
              <textarea rows={10} className="w-full font-mono text-[12px]" value={text} onChange={(e) => setText(e.target.value)} /></Field>
            <label className="mt-2 flex items-center gap-2 text-[12.5px] text-ink-2"><input type="checkbox" checked={useModel} onChange={(e) => setUseModel(e.target.checked)} /> Also ask a model from a different family (slower; it can raise concerns, never block)</label>
            <div className="mt-2"><Button variant="primary" busy={busy} onClick={review}>Review</Button></div>
            {res && <p role="status" className="mt-2 text-[13px]"><StatusBadge status={V_STATUS[res.verdict]} /> {res.summary}</p>}
          </Card>
          <Card title="Calibration cases" pad={false}>
            {cal && <Table head={["Case", "Expected", "Got"]} label="Calibration">{cal.cases.map((r: any) => <tr key={r.case}><td className="text-[12px]">{r.case}</td><td className="text-[12px]">{r.expected}</td>
              <td className={`text-[12px] ${r.ok ? "text-good" : "text-[#f08a8a]"}`}>{r.got}</td></tr>)}</Table>}
          </Card>
        </div>
      </div>
    </div>
  );
}

// ------------------------------------------------------------------ Account Vault
function Vault() {
  const v = useApi<any>("/api/accounts");
  const me = useMe();
  const [err, setErr] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [connect, setConnect] = useState<{ id: number; secret: string; accept: boolean } | null>(null);
  const [f, setF] = useState<any>({ service: "huggingface", identity: "", purpose: "", scopes: "read-repos", level: 2, paid: false, justification: {} });
  const run = async (fn: () => Promise<any>, ok: (r: any) => string) => { setErr(null); setMsg(null); try { setMsg(ok(await fn())); v.reload(); } catch (e) { setErr((e as Error).message); } };
  const d = v.data;
  return (
    <div className="space-y-4">
      <ErrorBanner error={err || v.error} />
      {msg && <p role="status" className="text-[13px] text-good">{msg}</p>}
      <p className="max-w-4xl text-[13px] text-ink-3">Agents never receive a password or key. They receive a <b className="text-ink-2">tool grant</b> that names an account; the tool runs on the server, uses the encrypted secret, and returns only the result. Every use is in the audit trail. Sign-ups are done by a person — e-mail and phone verification and CAPTCHAs are never bypassed — and one account per identity.</p>
      <Card title="Accounts" pad={false}>
        {d?.accounts?.length ? <Table head={["Account", "Level", "Scopes", "State", "Health", ""]} label="Accounts">{d.accounts.map((a: any) => (
          <Fragment key={a.id}><tr className="align-top">
            <td><div className="font-medium">{d.services[a.service]?.name ?? a.service} · {a.identity}</div><div className="text-[11.5px] text-ink-3">{a.purpose}</div>
              {a.critique_id && <Link className="text-[11.5px] text-violet underline underline-offset-2" href="/autonomy#advocate">critique #{a.critique_id}</Link>}
              {a.approval_id && <> · <Link className="text-[11.5px] text-violet underline underline-offset-2" href={`/approvals?id=${a.approval_id}`}>approval #{a.approval_id}</Link></>}</td>
            <td className="text-[12px]">{a.level} · {a.level_name}</td><td className="font-mono text-[11.5px]">{(a.scopes ?? []).join(", ") || "—"}</td>
            <td><StatusBadge status={a.status === "connected" ? "configured" : a.status === "pending_approval" ? "pending" : a.status} /></td>
            <td className="text-[12px]">{a.health?.checked_at ? <>{a.health.ok ? <span className="text-good">ok</span> : <span className="text-warning">{a.health.reason ?? "failed"}</span>}{a.health.identity && <> · {a.health.identity}</>}
              <div className="text-ink-3">{ago(a.last_health_at)}</div>{a.health.expiry_warning && <div className="text-warning">{a.health.expiry_warning}</div>}</> : "—"}</td>
            <td><div className="flex flex-wrap gap-1.5">
              {["pending_approval", "approved", "proposed"].includes(a.status) && me?.role === "admin" && a.level >= 1 && <Button onClick={() => setConnect({ id: a.id, secret: "", accept: false })}>Connect token</Button>}
              {a.status === "connected" && <Button onClick={() => run(() => api(`/api/accounts/${a.id}/health`, { method: "POST" }), (r) => r.ok ? `Healthy: ${r.identity}` : `Not healthy: ${r.reason ?? r.status}`)}>Check</Button>}
              {!["revoked", "rejected"].includes(a.status) && <Button variant="danger" onClick={() => run(() => api(`/api/accounts/${a.id}/revoke`, { method: "POST" }), () => "Revoked: secret disconnected, tool grants removed.")}>Revoke</Button>}
            </div></td></tr>
            {connect && connect.id === a.id && <tr><td colSpan={6}><div className="grid grid-cols-1 gap-2 py-2 md:grid-cols-[minmax(0,1fr)_auto]">
              <Field label={`Token you created at ${d.services[a.service]?.token ?? a.service} (stored encrypted; never shown again)`}>
                <input type="password" autoComplete="off" value={connect.secret} onChange={(e) => setConnect((c) => c && { ...c, secret: e.target.value })} /></Field>
              <label className="flex items-start gap-2 text-[12px] text-ink-2 md:col-span-2"><input type="checkbox" checked={connect.accept} onChange={(e) => setConnect((c) => c && { ...c, accept: e.target.checked })} /> {d.attestation}</label>
              <div><Button variant="primary" disabled={connect.secret.length < 8 || !connect.accept} onClick={() => run(() => api(`/api/accounts/${a.id}/connect`,
                { method: "POST", json: { secret: connect.secret, attestation: d.attestation } }), (r) => { setConnect(null); return `Connected: ${r.health?.ok ? `verified as ${r.health.identity}` : `stored, but the check failed (${r.health?.reason ?? "see health"})`}`; })}>Connect</Button></div>
            </div></td></tr>}
          </Fragment>))}</Table> : <div className="p-4"><Empty title={v.loading ? "Loading…" : "No accounts"}>Propose one below; agents can prepare requests too.</Empty></div>}
      </Card>
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <Card title="Propose an account (reviewed by the Devil's Advocate; level 2+ needs a second approver)">
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            <Field label="Service"><select value={f.service} onChange={(e) => setF({ ...f, service: e.target.value, scopes: (d?.services[e.target.value]?.recommended_scopes ?? []).join(", ") })}>
              {Object.entries(d?.services ?? {}).map(([k, s]: any) => <option key={k} value={k}>{s.name}</option>)}</select></Field>
            <Field label="Account / organisation name"><input value={f.identity} onChange={(e) => setF({ ...f, identity: e.target.value })} /></Field>
            <Field label="Purpose"><input value={f.purpose} onChange={(e) => setF({ ...f, purpose: e.target.value })} /></Field>
            <Field label="Scopes (comma-separated, least privilege)"><input value={f.scopes} onChange={(e) => setF({ ...f, scopes: e.target.value })} /></Field>
            <Field label="Level"><select value={f.level} onChange={(e) => setF({ ...f, level: Number(e.target.value) })}>{Object.entries(d?.levels ?? {}).map(([k, n]: any) => <option key={k} value={k}>{k} · {n}</option>)}</select></Field>
            <label className="flex items-end gap-2 pb-2 text-[12.5px] text-ink-2"><input type="checkbox" checked={f.paid} onChange={(e) => setF({ ...f, paid: e.target.checked })} /> paid service</label>
            {Object.entries(d?.justification ?? {}).map(([k, q]: any) => <Field key={k} label={q}><input value={f.justification[k] ?? ""} onChange={(e) => setF({ ...f, justification: { ...f.justification, [k]: e.target.value } })} /></Field>)}
          </div>
          <div className="mt-3"><Button variant="primary" disabled={!f.identity || f.purpose.length < 5} onClick={() => run(() => api("/api/accounts", { method: "POST", json: {
            ...f, scopes: f.scopes.split(",").map((s: string) => s.trim()).filter(Boolean) } }), (r) => `Account #${r.id}: ${r.status.replace("_", " ")}${r.approval_id ? ` — approval #${r.approval_id}` : ""} (critique #${r.critique_id})`)}>Propose</Button></div>
        </Card>
        <Card title="Services (how to connect them legitimately)">
          <ul className="space-y-3 text-[12.5px]">{Object.entries(d?.services ?? {}).map(([k, s]: any) => (
            <li key={k}><div className="font-medium">{s.name} <span className="text-ink-3">— {s.use}</span></div>
              <div className="text-ink-3">Sign-up: {s.signup}</div><div className="text-ink-3">Token: {s.token}</div>
              <div className="text-ink-3">Recommended scopes: <span className="font-mono">{(s.recommended_scopes ?? []).join(", ")}</span> · {s.free}</div></li>))}</ul>
        </Card>
      </div>
    </div>
  );
}
