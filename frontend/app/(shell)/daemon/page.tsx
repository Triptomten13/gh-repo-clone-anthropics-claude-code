"use client";
import { useDialog } from "@/components/dialog";
import { useEffect, useState } from "react";
import { CheckCircle2, CloudOff, Cpu, OctagonX, ShieldCheck } from "lucide-react";
import { LocalExternalBars } from "@/components/charts";
import { Button, Card, Empty, ErrorBanner, Field, PageHeader, Stat, StatusBadge, Table } from "@/components/ui";
import { ago, api } from "@/lib/api";
import { useApi } from "@/lib/hooks";

const TABS = ["Status", "Models", "Costs", "Providers & keys", "Benchmarks", "Optimisation", "Prompts & tools", "Workers & lab"] as const;
type Tab = (typeof TABS)[number];
const input = "rounded-md border border-line-strong bg-bg px-2.5 py-1.5 text-[13px] text-ink outline-none focus:border-violet";
const gb = (b: number) => `${(b / 1e9).toFixed(b > 1e10 ? 0 : 1)} GB`;
const usd = (v: number | null | undefined, d = 4) => (v === null || v === undefined ? "—" : `$${v.toFixed(d)}`);

export default function DaemonCore() {
  const [tab, setTab] = useState<Tab>("Status");
  const [err, setErr] = useState<string | null>(null);
  const status = useApi<any>("/api/ai/status");
  const act = async (fn: () => Promise<unknown>, after?: () => void) => {
    try { await fn(); setErr(null); after?.(); status.reload(); } catch (e) { setErr((e as Error).message); }
  };
  const s = status.data;
  return (
    <>
      <PageHeader kicker="Demonkoncernen · sovereign AI infrastructure" title="DAEMON CORE">
        {s && <span className={`inline-flex items-center gap-1.5 rounded-md border px-2.5 py-1 font-mono text-[11px] uppercase tracking-wider ${s.offline_mode ? "border-cyan/50 text-cyan" : "border-line-strong text-ink-2"}`}>
          {s.offline_mode ? <CloudOff size={13} /> : <Cpu size={13} />}{s.offline_mode ? "offline mode" : "online"} · {s.profile}</span>}
      </PageHeader>
      <ErrorBanner error={err ?? status.error} />
      <nav className="mb-5 flex flex-wrap gap-1 border-b border-line" aria-label="DAEMON sections">
        {TABS.map((t) => (
          <button key={t} onClick={() => setTab(t)} aria-current={tab === t ? "page" : undefined}
            className={`-mb-px border-b-2 px-3 py-2 text-[13px] transition ${tab === t ? "border-violet text-ink" : "border-transparent text-ink-3 hover:text-ink-2"}`}>{t}</button>
        ))}
      </nav>
      {tab === "Status" && <StatusTab s={s} act={act} />}
      {tab === "Models" && <ModelsTab act={act} />}
      {tab === "Costs" && <CostsTab act={act} />}
      {tab === "Providers & keys" && <ProvidersTab act={act} />}
      {tab === "Benchmarks" && <BenchTab act={act} />}
      {tab === "Optimisation" && <ProposalsTab act={act} />}
      {tab === "Prompts & tools" && <PromptsTab act={act} />}
      {tab === "Workers & lab" && <WorkersTab act={act} />}
    </>
  );
}

type Act = (fn: () => Promise<unknown>, after?: () => void) => Promise<void>;

function StatusTab({ s, act }: { s: any; act: Act }) {
  const settings = useApi<any>("/api/daemon/settings");
  const [test, setTest] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const runTest = async () => { setBusy(true); try { setTest(await api("/api/daemon/selftest", { method: "POST" })); } finally { setBusy(false); } };
  const patch = (json: any) => act(() => api("/api/daemon/settings", { method: "PATCH", json }), settings.reload);
  if (!s) return <Empty title="Loading DAEMON status…" />;
  const ind = s.independence;
  return (
    <>
      <div className={`mb-4 flex items-start gap-3 rounded-lg border px-4 py-3 ${ind.independent ? "border-good/40 bg-good/5" : "border-warning/50 bg-warning/5"}`}>
        {ind.independent ? <ShieldCheck className="mt-0.5 text-good" size={18} /> : <OctagonX className="mt-0.5 text-warning" size={18} />}
        <div>
          <div className="font-serif text-[16px] font-semibold">{ind.independent ? "Core AI runs on Demonkoncernen hardware" : "Not independent yet"}</div>
          <div className="text-[13px] text-ink-2">{ind.statement}</div>
          {ind.optional_external.length > 0 && <div className="mt-1 text-[12px] text-ink-3">Optional external: {ind.optional_external.join(" · ")}</div>}
          <div className="mt-1 text-[11.5px] text-ink-3">Install-time only: {ind.install_time_external.join(" · ")}</div>
        </div>
      </div>
      <div className="mb-4 grid grid-cols-2 gap-3 md:grid-cols-5">
        <Stat label="Chat model" value={<span className="text-[14px]">{s.active_models.chat ?? "none"}</span>} sub="standard tier" accent />
        <Stat label="Deep reasoning" value={<span className="text-[14px]">{s.active_models.deep ?? "none — falls back to chat"}</span>} sub="deep tier · thinks before answering" />
        <Stat label="Eco model" value={<span className="text-[14px]">{s.active_models.eco ?? "none"}</span>} sub="fast / classification" />
        <Stat label="Embeddings" value={<span className="text-[14px]">{s.active_models.embedding ?? "lexical hash (fallback)"}</span>} sub="Archive search" />
        <Stat label="Hardware" value={<span className="text-[14px]">{s.hardware.cores} cores · {s.hardware.ram_total_gb} GB</span>} sub={`${s.hardware.accelerator.toUpperCase()} · llama.cpp ${s.hardware.runtime.llama_cpp ? s.hardware.runtime.llama_cpp_version : "not installed"}`} />
      </div>
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <Card title="Operating mode">
          {settings.data && <div className="space-y-4">
            <label className="flex items-center justify-between gap-3">
              <span><span className="block text-[13.5px] font-medium">Offline mode</span><span className="text-[12px] text-ink-3">No external provider is ever called — not even as a fallback. Downloads disabled.</span></span>
              <button role="switch" aria-checked={settings.data.offline_mode} onClick={() => patch({ offline_mode: !settings.data.offline_mode })}
                className={`h-6 w-11 shrink-0 rounded-full border transition ${settings.data.offline_mode ? "border-cyan bg-cyan/30" : "border-line-strong bg-surface-2"}`}>
                <span className={`block h-4 w-4 translate-y-0 rounded-full bg-ink transition ${settings.data.offline_mode ? "translate-x-6" : "translate-x-1"}`} />
              </button>
            </label>
            <label className="flex items-center justify-between gap-3">
              <span><span className="block text-[13.5px] font-medium">External providers allowed</span><span className="text-[12px] text-ink-3">Master switch for paid APIs (still bounded by spend limits).</span></span>
              <button role="switch" aria-checked={settings.data.external_allowed} onClick={() => patch({ external_allowed: !settings.data.external_allowed })}
                className={`h-6 w-11 shrink-0 rounded-full border transition ${settings.data.external_allowed ? "border-violet bg-violet/30" : "border-line-strong bg-surface-2"}`}>
                <span className={`block h-4 w-4 rounded-full bg-ink transition ${settings.data.external_allowed ? "translate-x-6" : "translate-x-1"}`} />
              </button>
            </label>
            <Field label="Execution profile">
              <select className={input} value={settings.data.profile} onChange={(e) => patch({ profile: e.target.value })}>
                {Object.keys(s.profiles).map((p) => <option key={p} value={p}>{p} — {s.profiles[p].summary}</option>)}
              </select>
            </Field>
            <Field label="Deep reasoning: thinking budget (tokens) — more = slower but fewer unfinished thoughts">
              <select className={input} value={settings.data.local.thinking_tokens ?? 1536} onChange={(e) => patch({ local: { thinking_tokens: Number(e.target.value) } })}>
                {[512, 1024, 1536, 2048, 3072, 4096, 8192].map((n) => <option key={n} value={n}>{n.toLocaleString()} tokens{n === 1536 ? " (default)" : ""}</option>)}
              </select>
            </Field>
          </div>}
        </Card>
        <Card title="Routing right now" pad={false}>
          <Table head={["Tier", "Order tried", "Excluded by policy"]}>
            {Object.entries(s.chains).map(([tier, c]: any) => <tr key={tier} className="align-top"><td className="font-medium">{tier}</td>
              <td className="font-mono text-[11.5px]">{c.order.length ? c.order.map((o: string) => <div key={o}>{o}</div>) : <span className="text-warning">nothing permitted</span>}</td>
              <td className="font-mono text-[11px] text-ink-3">{c.excluded.map((o: string) => <div key={o}>{o}</div>)}</td></tr>)}
          </Table>
          <div className="p-3 text-[11.5px] text-ink-3">Cheapest adequate first. Refusals are never re-routed; failures fall through; paid calls are checked against spend limits first.</div>
        </Card>
      </div>
      <Card title="Self-test" className="mt-4" action={<Button busy={busy} onClick={runTest}>Run self-test</Button>} pad={!test}>
        {!test ? <p className="text-[13px] text-ink-3">Runs every check for real: database, runtime, a local generation, local embeddings, that the OFFLINE profile contains no external provider, Archive, memory and agents.</p> :
          <Table head={["Check", "Result", "Detail", "ms"]}>{test.checks.map((c: any) => <tr key={c.check}><td className="font-medium">{c.check.replaceAll("_", " ")}</td>
            <td>{c.ok ? <span className="inline-flex items-center gap-1 text-good"><CheckCircle2 size={13} />pass</span> : <span className="inline-flex items-center gap-1 text-[#f08a8a]"><OctagonX size={13} />fail</span>}</td>
            <td className="max-w-lg truncate font-mono text-[11px] text-ink-3" title={JSON.stringify(c.detail)}>{typeof c.detail === "string" ? c.detail : JSON.stringify(c.detail)}</td><td className="num">{c.ms}</td></tr>)}</Table>}
      </Card>
    </>
  );
}

function ModelsTab({ act }: { act: Act }) {
  const dlg = useDialog();
  const lib = useApi<any>("/api/daemon/library");
  useEffect(() => {
    if (!lib.data?.models?.some((m: any) => m.status === "downloading")) return;
    const t = setInterval(lib.reload, 2500);
    return () => clearInterval(t);
  }, [lib.data, lib.reload]);
  const slotFor = (m: any) => (m.kind === "embedding" ? ["embedding"] : m.capabilities?.includes("thinking") ? ["deep", "chat"] : ["chat", "eco"]);
  return (
    <Card title="Model library" pad={false} action={<span className="text-[11px] text-ink-3">catalog verified {lib.data?.catalog_verified_at}</span>}>
      {!lib.data ? <div className="p-4"><Empty title="Loading…" /></div> : (
        <Table head={["Model", "Kind", "Size", "Licence", "Fits here?", "Status", "Active", ""]}>
          {lib.data.models.map((m: any) => (
            <tr key={m.key} className="align-top">
              <td><div className="font-medium">{m.display_name}</div><code className="text-[11px] text-ink-3">{m.source_repo}</code>
                {m.sha256_actual && <div className="font-mono text-[10.5px] text-ink-3" title={m.sha256_actual}>sha256 {m.sha256_actual.slice(0, 12)}… verified</div>}</td>
              <td className="text-ink-2">{m.kind}<div className="text-[11px] text-ink-3">{m.parameters} · {m.quantization}</div></td>
              <td className="num">{gb(m.size_bytes)}</td>
              <td><div className="font-mono text-[12px]">{m.license}</div><StatusBadge status={m.commercial_use} /></td>
              <td><StatusBadge status={m.fit.verdict} /><div className="text-[11px] text-ink-3">needs ~{gb(m.fit.ram_needed_bytes)}</div></td>
              <td><StatusBadge status={m.status} />{m.status === "downloading" && <div className="num text-[11px] text-ink-3">{Math.round((100 * m.progress_bytes) / m.size_bytes)}%</div>}
                {m.error && <div className="max-w-[16rem] text-[11px] text-[#f3a5a5]">{m.error}</div>}</td>
              <td className="text-[12px] text-violet">{m.active_slots.join(", ") || "—"}</td>
              <td className="whitespace-nowrap text-right">
                {(m.status === "available" || m.status === "failed" || m.status === "removed") &&
                  <Button disabled={m.fit.verdict === "does_not_fit"} onClick={() => act(() => api(`/api/daemon/library/${m.key}/install`, { method: "POST" }), lib.reload)}>Install</Button>}
                {m.runnable && slotFor(m).filter((sl) => !m.active_slots.includes(sl)).map((sl) =>
                  <Button key={sl} onClick={() => act(() => api("/api/daemon/library/activate", { method: "POST", json: { slot: sl, key: m.key } }), lib.reload)}>Use as {sl}</Button>)}
                {m.status === "installed" && !m.active_slots.length && <Button variant="danger" onClick={async () => { if (await dlg.confirm({ title: `Delete ${m.key}?`, message: "The model weights are removed from disk. Re-installing downloads them again.", confirmLabel: "Delete weights", danger: true })) act(() => api(`/api/daemon/library/${m.key}`, { method: "DELETE" }), lib.reload); }}>Remove</Button>}
              </td>
            </tr>
          ))}
        </Table>
      )}
      <div className="flex flex-wrap items-center gap-2 border-t border-line p-3 text-[11.5px] text-ink-3">
        <span>Roll back a slot to its previous model:</span>
        {["chat", "deep", "eco", "embedding"].map((sl) => <Button key={sl} onClick={() => act(() => api("/api/daemon/library/rollback", { method: "POST", json: { slot: sl } }), lib.reload)}>{sl}</Button>)}
        <span className="basis-full">Licences come from each repository&apos;s own model-card metadata; open weights are not automatically unrestricted. Downloads come only from huggingface.co and are refused on any checksum or licence mismatch. Offline installs: <code>POST /api/daemon/library/&lt;key&gt;/import-file</code> with a checksum-matching file. After changing the embedding model, re-embed the Archive.</span>
      </div>
    </Card>
  );
}

function CostsTab({ act }: { act: Act }) {
  const [days, setDays] = useState(30);
  const c = useApi<any>(`/api/daemon/costs?days=${days}`, [days]);
  const settings = useApi<any>("/api/daemon/settings");
  const [lim, setLim] = useState<{ daily: string; monthly: string }>({ daily: "", monthly: "" });
  useEffect(() => { if (settings.data) setLim({ daily: settings.data.limits.daily_usd ?? "", monthly: settings.data.limits.monthly_usd ?? "" }); }, [settings.data]);
  if (!c.data) return <Empty title="Loading cost intelligence…" />;
  const t = c.data.totals;
  const daysData = Object.entries(c.data.by_day).map(([date, v]: any) => ({ date, local: v.local_calls, external: Math.max(0, v.calls - v.local_calls - v.failed) }));
  const dim = (title: string, data: Record<string, any>) => (
    <Card title={title} pad={false}>
      {Object.keys(data).length ? <Table head={["", "Calls", "Local", "Tokens", "API cost", "Failed"]}>{Object.entries(data).sort((a: any, b: any) => b[1].cost_usd - a[1].cost_usd || b[1].calls - a[1].calls).slice(0, 12).map(([k, v]: any) =>
        <tr key={k}><td className="max-w-[14rem] truncate font-mono text-[11.5px]" title={k}>{k}</td><td className="num">{v.calls}</td><td className="num">{v.local_calls}</td><td className="num">{Math.round(v.tokens).toLocaleString()}</td><td className="num">{usd(v.cost_usd)}</td><td className="num">{v.failed}</td></tr>)}</Table>
        : <div className="p-4 text-[12.5px] text-ink-3">No calls in this window.</div>}
    </Card>
  );
  return (
    <>
      <div className="mb-3 flex items-center gap-2 text-[12px] text-ink-3">Window:
        {[7, 30, 90].map((d) => <button key={d} onClick={() => setDays(d)} className={`rounded border px-2 py-0.5 ${d === days ? "border-violet text-ink" : "border-line-strong"}`}>{d} d</button>)}</div>
      <div className="mb-4 grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        <Stat label="External API cost" value={usd(t.external_cost_usd)} sub="list prices" accent />
        <Stat label="Local share" value={`${Math.round(t.local_share * 100)}%`} sub={`${t.local_calls ?? 0} local · ${t.external_calls ?? 0} external`} />
        <Stat label="Local energy (est.)" value={`${(t.energy_wh ?? 0).toFixed(2)} Wh`} sub={`≈ ${usd(t.local_energy_cost_usd_estimate)}`} />
        <Stat label="Tokens" value={Math.round((t.input_tokens ?? 0) + (t.output_tokens ?? 0)).toLocaleString()} sub={`cached: ${Math.round((t.response_cache_tokens ?? 0) + (t.provider_cached_tokens ?? 0)).toLocaleString()}`} />
        <Stat label="Savings" value={usd(c.data.savings.actual_usd)} sub={`actual · est. ${usd(c.data.savings.estimated_usd)}`} />
        <Stat label="Month forecast" value={usd(c.data.forecast.projected_month_usd, 2)} sub={`MTD ${usd(c.data.forecast.month_to_date_usd, 2)}`} />
      </div>
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
        <Card title="Where work ran" className="xl:col-span-2">{daysData.length ? <LocalExternalBars data={daysData} /> : <Empty title="No AI calls yet" />}</Card>
        <Card title="Spending limits">
          <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); act(() => api("/api/daemon/settings", { method: "PATCH", json: { limits: { daily_usd: lim.daily === "" ? null : Number(lim.daily), monthly_usd: lim.monthly === "" ? null : Number(lim.monthly) } } }), settings.reload); }}>
            <Field label="Daily external spend cap (USD, empty = server default)"><input className={input} inputMode="decimal" value={lim.daily} onChange={(e) => setLim({ ...lim, daily: e.target.value })} /></Field>
            <Field label="Monthly external spend cap (USD)"><input className={input} inputMode="decimal" value={lim.monthly} onChange={(e) => setLim({ ...lim, monthly: e.target.value })} /></Field>
            <Button type="submit">Save limits</Button>
          </form>
          <p className="mt-3 text-[11.5px] text-ink-3">Paid calls that would exceed a cap are not made — the task is blocked and shown here. Failed requests: {t.failed ?? 0}; excluded by policy: {t.excluded_by_policy ?? 0}.</p>
        </Card>
      </div>
      <div className="mt-4 grid grid-cols-1 gap-4 xl:grid-cols-2">
        {dim("Cost per agent", c.data.by_agent)}
        {dim("Cost per workflow", c.data.by_workflow)}
        {dim("Cost per model", c.data.by_model)}
        {dim("Cost per project", c.data.by_project)}
      </div>
      <p className="mt-3 text-[11.5px] text-ink-3">{c.data.note} {c.data.savings.basis}. Forecast: {c.data.forecast.method}.</p>
    </>
  );
}

function ProvidersTab({ act }: { act: Act }) {
  const dlg = useDialog();
  const provs = useApi<any[]>("/api/daemon/providers");
  const creds = useApi<any>("/api/daemon/credentials");
  const [f, setF] = useState({ provider: "anthropic", label: "", secret: "", attest: false });
  return (
    <>
      <Card title="Provider registry" pad={false}>
        <Table head={["Provider", "Kind", "Status", "Facts on record", "Verified", ""]}>
          {(provs.data ?? []).map((p) => (
            <tr key={p.id} className="align-top">
              <td><div className="font-medium">{p.name}</div>{p.website && <a className="text-[11.5px] text-violet hover:underline" href={p.website} target="_blank" rel="noreferrer">{p.website.replace("https://", "")} ↗</a>}</td>
              <td className="text-ink-2">{p.kind.replace("_", " ")}{p.adapter && <div className="text-[11px] text-ink-3">adapter in code</div>}</td>
              <td><StatusBadge status={p.paused ? "paused" : p.status} /></td>
              <td className="max-w-md text-[11.5px] text-ink-3">{Object.entries(p.facts ?? {}).slice(0, 5).map(([k, v]) => <div key={k}><span className="text-ink-2">{k.replaceAll("_", " ")}:</span> {typeof v === "string" ? v : JSON.stringify(v)}</div>)}</td>
              <td className="text-[12px] text-ink-3">{p.last_verified_at ? <><span className="num">{String(p.last_verified_at).slice(0, 10)}</span><div className="text-[11px]">{p.verified_by}</div></> : "never"}</td>
              <td className="whitespace-nowrap text-right">
                {p.kind === "api" && p.adapter && <Button onClick={() => act(() => api(`/api/daemon/providers/${p.id}/pause`, { method: "POST", json: { paused: !p.paused } }), provs.reload)}>{p.paused ? "Resume" : "Pause"}</Button>}{" "}
                <Button onClick={async () => { const url = await dlg.prompt({ title: `Verify ${p.name}`, message: "Record the official documentation page you checked the pricing and terms against.", label: "Documentation URL", inputType: "url", confirmLabel: "Record verification" }); if (url) act(() => api(`/api/daemon/providers/${p.id}/verify`, { method: "POST", json: { source_url: url, notes: "verified by admin" } }), provs.reload); }}>Record verification</Button>
              </td>
            </tr>
          ))}
        </Table>
        <p className="p-3 text-[11.5px] text-ink-3">Free tiers, quotas and prices are never assumed. A discovered provider stays &quot;unverified&quot; with unknown facts until someone checks its official documentation and records the URL here.</p>
      </Card>
      <Card title="Credentials (owner-authorised, encrypted at rest)" className="mt-4" pad={false}>
        {creds.error ? <div className="p-4 text-[13px] text-ink-3">Admins only.</div> : <>
          <Table head={["Provider", "Label", "Key", "Status", "Last test", ""]}>
            {(creds.data?.credentials ?? []).map((c: any) => (
              <tr key={c.id}>
                <td className="font-medium">{c.provider}</td><td className="text-ink-2">{c.label || "—"}</td><td className="font-mono text-[12px]">{c.fingerprint}</td>
                <td><StatusBadge status={c.status} />{c.expiring_soon && <span className="ml-1 text-[11px] text-warning">expires soon</span>}</td>
                <td className="text-[12px] text-ink-3">{c.last_validated_at ? `${c.last_validation?.ok ? "ok" : "failed"} · ${ago(c.last_validated_at)}` : "never"}</td>
                <td className="whitespace-nowrap text-right">{c.status === "active" && <>
                  <Button onClick={() => act(() => api(`/api/daemon/credentials/${c.id}/validate`, { method: "POST" }), creds.reload)}>Test</Button>{" "}
                  <Button onClick={async () => { const sec = await dlg.prompt({ title: "Rotate secret", message: "The new secret replaces the stored one; it is encrypted at rest and never shown again.", label: "New secret", inputType: "password", confirmLabel: "Rotate" }); if (sec) act(() => api(`/api/daemon/credentials/${c.id}/rotate`, { method: "POST", json: { secret: sec } }), creds.reload); }}>Rotate</Button>{" "}
                  <Button variant="danger" onClick={async () => { if (await dlg.confirm({ title: "Disconnect this credential?", message: "The stored secret is destroyed. Calls that need it stop until a new one is added.", confirmLabel: "Disconnect", danger: true })) act(() => api(`/api/daemon/credentials/${c.id}`, { method: "DELETE" }), creds.reload); }}>Disconnect</Button></>}</td>
              </tr>
            ))}
          </Table>
          <form className="space-y-3 border-t border-line p-4" onSubmit={(e) => { e.preventDefault(); act(() => api("/api/daemon/credentials", { method: "POST", json: { provider: f.provider, label: f.label, secret: f.secret, attestation: creds.data.attestation_text } }), () => { setF({ ...f, secret: "", attest: false }); creds.reload(); }); }}>
            <div className="flex flex-wrap items-end gap-2">
              <Field label="Provider"><input className={input} value={f.provider} onChange={(e) => setF({ ...f, provider: e.target.value })} /></Field>
              <Field label="Label"><input className={input} value={f.label} onChange={(e) => setF({ ...f, label: e.target.value })} /></Field>
              <Field label="API key"><input className={input} type="password" autoComplete="off" required minLength={8} value={f.secret} onChange={(e) => setF({ ...f, secret: e.target.value })} /></Field>
            </div>
            <label className="flex items-start gap-2 text-[12.5px] text-ink-2"><input type="checkbox" className="mt-0.5" checked={f.attest} onChange={(e) => setF({ ...f, attest: e.target.checked })} />{creds.data?.attestation_text}</label>
            <Button type="submit" variant="primary" disabled={!f.attest}>Store credential</Button>
            <p className="text-[11.5px] text-ink-3">One active key per provider — never a pool to rotate around rate limits. Keys are never shown again, never logged and never given to agents.</p>
          </form>
        </>}
      </Card>
    </>
  );
}

function BenchTab({ act }: { act: Act }) {
  const b = useApi<any>("/api/daemon/benchmarks");
  const running = b.data?.runs?.some((r: any) => r.status === "running");
  useEffect(() => { if (!running) return; const t = setInterval(b.reload, 3000); return () => clearInterval(t); }, [running, b.reload]);
  const start = (model: string) => act(() => api("/api/daemon/benchmarks/run", { method: "POST", json: { provider: "local", model } }), b.reload);
  return (
    <Card title="Model benchmark — cost per successful task" action={<span className="flex flex-wrap gap-2"><Button busy={running} onClick={() => start("deep")}>Run on local deep</Button><Button busy={running} onClick={() => start("chat")}>Run on local chat</Button><Button busy={running} onClick={() => start("eco")}>Run on local eco</Button></span>} pad={false}>
      {b.data?.runs?.length ? <Table head={["Model", "Status", "Accuracy", "By skill", "Avg latency", "API cost", "Energy (est.)", "Cost / success", "When"]}>
        {b.data.runs.map((r: any) => <tr key={r.id} className="align-top"><td><div className="whitespace-nowrap font-mono text-[12px]">{r.model}</div><div className="text-[11px] text-ink-3">{r.provider}</div></td>
          <td><StatusBadge status={r.status} /></td><td className="num">{r.summary?.accuracy !== undefined ? `${Math.round(r.summary.accuracy * 100)}% (${r.summary.passed}/${r.summary.tasks})` : "—"}</td>
          <td className="min-w-[14rem] max-w-[24rem] whitespace-normal text-[11px] text-ink-3">{r.summary?.by_skill && Object.entries(r.summary.by_skill).map(([k, v]: any) => <span key={k} className={`mr-2 inline-block whitespace-nowrap ${v < 0.5 ? "text-warning" : ""}`}>{k.replaceAll("_", " ")} {Math.round(v * 100)}%</span>)}</td>
          <td className="num">{r.summary?.avg_latency_ms ?? "—"} ms</td><td className="num">{usd(r.summary?.api_cost_usd)}</td><td className="num">{r.summary?.energy_wh_estimate ?? "—"} Wh</td>
          <td className="num">{usd(r.summary?.cost_per_success_usd, 6)}</td><td className="text-ink-3">{ago(r.started_at)}</td></tr>)}
      </Table> : <div className="p-4"><Empty title="No benchmark runs yet">Seventeen graded tasks: classification, structured output, instruction adherence, reasoning, seven multi-step deep-reasoning problems, abstention, context, coding (static check — generated code is never run), tool-call format.</Empty></div>}
      <p className="p-3 text-[11.5px] text-ink-3">A cheap model that fails is not cheap: cost per success = (API cost + estimated electricity) ÷ passed tasks. External models can be benchmarked via the API with explicit spend authorisation.</p>
    </Card>
  );
}

function ProposalsTab({ act }: { act: Act }) {
  const p = useApi<any[]>("/api/daemon/proposals");
  return (
    <Card title="Optimisation proposals" action={<Button onClick={() => act(() => api("/api/daemon/proposals/generate", { method: "POST" }), p.reload)}>Analyse usage</Button>} pad={false}>
      {p.data?.length ? <Table head={["Proposal", "Evidence", "Est. saving", "Status", ""]}>
        {p.data.map((o) => <tr key={o.id} className="align-top"><td><div className="font-medium">{o.title}</div><div className="text-[12px] text-ink-3">{o.detail}</div></td>
          <td className="font-mono text-[11px] text-ink-3">{JSON.stringify(o.evidence)}</td><td className="num">{o.estimated_saving_usd === null ? "—" : usd(o.estimated_saving_usd)}</td>
          <td><StatusBadge status={o.status} /></td>
          <td className="whitespace-nowrap text-right">{o.status === "proposed" && <><Button onClick={() => act(() => api(`/api/daemon/proposals/${o.id}/decide`, { method: "POST", json: { approve: true } }), p.reload)}>Approve</Button>{" "}
            <Button variant="danger" onClick={() => act(() => api(`/api/daemon/proposals/${o.id}/decide`, { method: "POST", json: { approve: false } }), p.reload)}>Reject</Button></>}</td></tr>)}
      </Table> : <div className="p-4"><Empty title="No proposals">Analyse usage to find premium models used for short answers, repeated paid prompts, work a local model could do, rate-limit trouble, oversized contexts and stale provider facts.</Empty></div>}
      <p className="p-3 text-[11.5px] text-ink-3">Approval records the decision; it never changes spending, credentials, accounts or provider terms by itself.</p>
    </Card>
  );
}

function PromptsTab({ act }: { act: Act }) {
  const pr = useApi<any[]>("/api/daemon/prompts");
  const tools = useApi<any[]>("/api/daemon/tools");
  const names = Array.from(new Set((pr.data ?? []).map((x) => x.name)));
  return (
    <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
      <Card title="Versioned prompts" pad={false}>
        {names.map((n) => {
          const versions = (pr.data ?? []).filter((x) => x.name === n);
          const active = versions.find((v) => v.active);
          return <div key={n} className="border-b border-line p-4 last:border-0">
            <div className="mb-1 flex items-center justify-between gap-2"><code className="text-[12.5px] text-violet">{n}</code>
              <select aria-label={`Active version of ${n}`} className={input} value={active?.version} onChange={(e) => act(() => api(`/api/daemon/prompts/${n}/activate`, { method: "POST", json: { version: Number(e.target.value) } }), pr.reload)}>
                {versions.map((v) => <option key={v.version} value={v.version}>v{v.version}{v.active ? " (active)" : ""} · {v.created_by}</option>)}</select></div>
            <pre className="max-h-40 overflow-auto whitespace-pre-wrap rounded bg-bg p-2 font-mono text-[11px] text-ink-2">{active?.text}</pre>
            <div className="mt-1 text-[11px] text-ink-3">~{active?.estimated_tokens} tokens (estimate){active?.variables?.length ? ` · variables: ${active.variables.join(", ")}` : ""}</div>
          </div>;
        })}
      </Card>
      <Card title="Tools" pad={false}>
        <Table head={["Tool", "Level", "Side effects", "Status"]}>{(tools.data ?? []).map((t) => <tr key={t.name} className="align-top"><td><code className="text-[12px]">{t.name}</code><div className="text-[11.5px] text-ink-3">{t.description}</div>{t.blocked_reason && <div className="text-[11.5px] text-warning">{t.blocked_reason}</div>}</td>
          <td className="num">{t.permission_level}</td><td className="text-[12px] text-ink-3">{t.side_effects.replace("_", " ")}</td><td><StatusBadge status={t.status} /></td></tr>)}</Table>
      </Card>
    </div>
  );
}

function WorkersTab({ act }: { act: Act }) {
  const w = useApi<any[]>("/api/daemon/workers");
  const ft = useApi<any>("/api/daemon/finetune/feasibility");
  const hw = useApi<any>("/api/daemon/hardware");
  const [f, setF] = useState({ name: "", base_url: "http://192.168.1.20:8080", models: "" });
  return (
    <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
      <Card title="Inference workers (OpenAI-compatible)" pad={false}>
        {w.data?.length ? <Table head={["Name", "URL", "Locality", "Status", ""]}>{w.data.map((x) => <tr key={x.id}><td className="font-medium">{x.name}</td><td className="font-mono text-[11.5px]">{x.base_url}</td>
          <td className={x.locality === "external" ? "text-warning" : "text-ink-2"}>{x.locality}</td><td><StatusBadge status={x.status} /></td>
          <td className="whitespace-nowrap text-right"><Button onClick={() => act(() => api(`/api/daemon/workers/${x.id}/check`, { method: "POST" }), w.reload)}>Check</Button>{" "}
            <Button variant="danger" onClick={() => act(() => api(`/api/daemon/workers/${x.id}`, { method: "DELETE" }), w.reload)}>Remove</Button></td></tr>)}</Table>
          : <div className="p-4"><Empty title="No workers registered">Run llama.cpp server or vLLM on another machine you control and register it; it joins routing as local/LAN capacity.</Empty></div>}
        <form className="flex flex-wrap items-end gap-2 border-t border-line p-4" onSubmit={(e) => { e.preventDefault(); act(() => api("/api/daemon/workers", { method: "POST", json: { name: f.name, base_url: f.base_url, models: f.models.split(",").map((m) => m.trim()).filter(Boolean) } }), w.reload); }}>
          <Field label="Name"><input className={input} required pattern="[a-z0-9_-]{2,64}" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></Field>
          <Field label="Base URL"><input className={input} required value={f.base_url} onChange={(e) => setF({ ...f, base_url: e.target.value })} /></Field>
          <Field label="Models (comma)"><input className={input} value={f.models} onChange={(e) => setF({ ...f, models: e.target.value })} /></Field>
          <Button type="submit">Register</Button>
        </form>
      </Card>
      <Card title="Fine-tuning lab — feasibility">
        {ft.data && <div className="space-y-2 text-[13px]">
          {(["foundation_model_training", "full_fine_tune", "lora_adapter"] as const).map((k) => <div key={k} className="flex items-start gap-2">
            {ft.data[k].feasible ? <CheckCircle2 size={14} className="mt-0.5 text-good" /> : <OctagonX size={14} className="mt-0.5 text-[#f08a8a]" />}
            <div><span className="font-medium">{k.replaceAll("_", " ")}</span>: {ft.data[k].feasible ? "feasible" : "not feasible"}<div className="text-[12px] text-ink-3">{ft.data[k].reason ?? (ft.data[k].blockers ?? []).join("; ")}</div></div></div>)}
          <div className="text-[12px] text-ink-3">Available now instead: {ft.data.alternatives_available_now.join(" · ")}</div>
          <div className="text-[12px] text-ink-3">{ft.data.data_policy}</div>
        </div>}
        {hw.data && <div className="mt-4 border-t border-line pt-3 font-mono text-[11.5px] text-ink-3">
          <div>{hw.data.cpu.model} · {hw.data.cpu.usable_cores} cores · {hw.data.cpu.simd.join(" ")}</div>
          <div>RAM {gb(hw.data.ram_available_bytes)} free of {gb(hw.data.ram_total_bytes)} · disk free {gb(hw.data.disk_free_bytes)} · {hw.data.gpus.length ? hw.data.gpus.map((g: any) => g.name).join(", ") : "no GPU"}</div>
          <div>{hw.data.os} · Python {hw.data.python}</div>
        </div>}
      </Card>
    </div>
  );
}
