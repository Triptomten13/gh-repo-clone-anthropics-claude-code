"use client";
import { useCallback, useEffect, useState } from "react";
import { Activity, CloudOff, Cpu, Gauge, HardDrive, Network, Wallet } from "lucide-react";
import { Button, Card, Empty, ErrorBanner, PageHeader, Stat, StatusBadge, Table } from "@/components/ui";
import { api } from "@/lib/api";

const gb = (b?: number | null) => (b === null || b === undefined ? "—" : `${(b / 1e9).toFixed(1)} GB`);
const mb = (b?: number | null) => (b === null || b === undefined ? "—" : `${(b / 1e6).toFixed(b > 1e8 ? 0 : 1)} MB`);
const rate = (b?: number | null) => (b === null || b === undefined ? "—" : b > 1e6 ? `${(b / 1e6).toFixed(1)} MB/s` : `${(b / 1e3).toFixed(1)} kB/s`);
const usd = (v?: number | null, d = 4) => (v === null || v === undefined ? "—" : `$${v.toFixed(d)}`);
const pct = (v?: number | null) => (v === null || v === undefined ? "—" : `${Math.round(v * 100)}%`);

/** Poll while the page is visible; pause in background tabs (no wasted requests). */
function useLive<T>(path: string, everyMs: number) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(async () => {
    try { setData(await api<T>(path)); setError(null); } catch (e) { setError((e as Error).message); }
  }, [path]);
  useEffect(() => {
    load();
    let t: ReturnType<typeof setInterval> | null = setInterval(() => { if (!document.hidden) load(); }, everyMs);
    const onVis = () => { if (!document.hidden) load(); };
    document.addEventListener("visibilitychange", onVis);
    return () => { if (t) clearInterval(t); t = null; document.removeEventListener("visibilitychange", onVis); };
  }, [load, everyMs]);
  return { data, error, reload: load };
}

/** One-unit sparkline with min/max/current labelled — real samples only. */
function Spark({ values, label, fmt, tone = "stroke-cyan" }: { values: (number | null)[]; label: string; fmt: (v: number) => string; tone?: string }) {
  const v = values.filter((x): x is number => x !== null && x !== undefined);
  if (v.length < 2) return <div className="text-[12px] text-ink-3">{label}: collecting samples…</div>;
  const min = Math.min(...v), max = Math.max(...v), span = max - min || 1, w = 220, h = 36;
  const pts = v.map((x, i) => `${(i / (v.length - 1)) * w},${h - ((x - min) / span) * (h - 4) - 2}`).join(" ");
  return (
    <div>
      <div className="flex justify-between text-[11.5px] text-ink-3"><span>{label}</span><span className="num text-ink-2">{fmt(v[v.length - 1])}</span></div>
      <svg viewBox={`0 0 ${w} ${h}`} className="h-9 w-full" preserveAspectRatio="none" role="img" aria-label={`${label} over the last ${v.length} samples`}>
        <polyline points={pts} fill="none" className={tone} strokeWidth="1.5" vectorEffect="non-scaling-stroke" />
      </svg>
      <div className="flex justify-between text-[10.5px] text-ink-3"><span>min {fmt(min)}</span><span>max {fmt(max)}</span></div>
    </div>
  );
}

export default function ControlCenter() {
  const o = useLive<any>("/api/control/overview", 5000);
  const hist = useLive<any>("/api/control/history?points=120", 5000);
  const routes = useLive<any>("/api/control/routes", 15000);
  const d = o.data;
  const h = d?.hardware ?? {};
  const s = hist.data?.samples ?? [];
  const ramUsed = h.ram_total_bytes && h.ram_available_bytes !== null ? h.ram_total_bytes - h.ram_available_bytes : null;
  return (
    <>
      <PageHeader kicker="Demonkoncernen · real-time operations" title="DAEMON HYPERINTELLIGENCE">
        {d && <span className="inline-flex items-center gap-1.5 rounded-md border border-line-strong px-2.5 py-1 font-mono text-[11px] uppercase tracking-wider text-ink-2">
          {d.network.offline_mode ? <CloudOff size={13} className="text-cyan" /> : <Activity size={13} className="text-good" />}
          {d.network.offline_mode ? "offline" : "online"} · mode {d.intelligence.resource_mode.effective}
          {d.intelligence.resource_mode.effective !== d.intelligence.resource_mode.configured && <span className="text-warning"> (auto from {d.intelligence.resource_mode.configured})</span>}
        </span>}
      </PageHeader>
      <ErrorBanner error={o.error} />
      {!d ? <Empty title="Measuring…" /> : <>
        <div className="mb-4 grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
          <Stat label="RAM in use" value={gb(ramUsed)} sub={`of ${gb(h.ram_total_bytes)} · page cache ${gb(h.page_cache_bytes)}`} accent />
          <Stat label="CPU" value={h.cpu_pct === null || h.cpu_pct === undefined ? "—" : `${h.cpu_pct}%`} sub={h.cpu_temp_c ? `${h.cpu_temp_c} °C` : "temperature not exposed"} />
          <Stat label="This process" value={gb(h.process_rss_bytes)} sub={`${h.process_cpu_s ?? "—"} CPU-s · ${h.threads ?? "—"} threads`} />
          <Stat label="Task success (24 h)" value={pct(d.intelligence.task_success_rate_24h)} sub={`queued ${d.intelligence.queue.queued ?? 0} · running ${d.intelligence.queue.running ?? 0}`} />
          <Stat label="External cost today" value={usd(d.economics.today.external_cost_usd)} sub={`local share ${pct(d.economics.today.local_share)}`} />
          <Stat label="API latency p50" value={d.efficiency.api_latency.p50_ms === null ? "—" : `${d.efficiency.api_latency.p50_ms} ms`} sub="since process start" />
        </div>
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
          <Card title={<span className="inline-flex items-center gap-1.5"><Cpu size={13} />Intelligence</span>} pad={false}>
            <div className="grid grid-cols-2 gap-x-4 gap-y-1 p-4 text-[12.5px]">
              {Object.entries(d.intelligence.active_models).map(([slot, key]: any) => <div key={slot} className="contents"><span className="text-ink-3">{slot}</span><span className="truncate font-mono text-[11.5px]" title={key ?? ""}>{key ?? "none"}</span></div>)}
            </div>
            <Table head={["Resident model", "Size", "Idle", "Uses", ""]}>
              {d.intelligence.resident_models.length ? d.intelligence.resident_models.map((m: any) => <tr key={m.cache_key}>
                <td className="max-w-[12rem] truncate font-mono text-[11px]" title={m.cache_key}>{m.cache_key}</td><td className="num">{mb(m.size_bytes)}</td>
                <td className="num">{m.idle_s}s</td><td className="num">{m.uses}</td><td>{m.busy ? <StatusBadge status="running" /> : null}</td></tr>)
                : <tr><td colSpan={5} className="text-ink-3">no model in memory (loaded on demand)</td></tr>}
            </Table>
            <div className="p-3 text-[11.5px] text-ink-3">{d.intelligence.model_loads} loads · {d.intelligence.model_unloads} unloads · {(d.intelligence.load_ms_total / 1000).toFixed(1)} s spent loading · research runs 24 h: {d.intelligence.research_runs_24h} · monitors {d.intelligence.monitors} ({d.intelligence.unacknowledged_alerts} unread alerts)</div>
          </Card>
          <Card title={<span className="inline-flex items-center gap-1.5"><HardDrive size={13} />Hardware</span>}>
            <div className="space-y-3">
              <Spark values={s.map((x: any) => x.cpu_pct)} label="CPU %" fmt={(v) => `${v.toFixed(0)}%`} />
              <Spark values={s.map((x: any) => (x.ram_available_bytes === null ? null : x.ram_available_bytes / 1e9))} label="RAM available" fmt={(v) => `${v.toFixed(1)} GB`} tone="stroke-violet" />
              <Spark values={s.map((x: any) => (x.rss_bytes === null ? null : x.rss_bytes / 1e9))} label="Process RSS" fmt={(v) => `${v.toFixed(2)} GB`} tone="stroke-gold" />
            </div>
            <div className="mt-3 grid grid-cols-2 gap-y-1 text-[12px]">
              <span className="text-ink-3">Disk free</span><span className="num">{gb(h.disk_free_bytes)} of {gb(h.disk_total_bytes)}</span>
              <span className="text-ink-3">Disk read / write</span><span className="num">{rate(h.disk_read_bps)} / {rate(h.disk_write_bps)}</span>
              <span className="text-ink-3">GPU / VRAM</span><span>{h.vram ? h.vram.map((g: any) => `${g.name} ${g.free_mb}/${g.total_mb} MB free`).join(", ") : "no GPU detected"}</span>
              <span className="text-ink-3">Swap in use</span><span className="num">{gb(h.swap_used_bytes)}</span>
            </div>
          </Card>
          <Card title={<span className="inline-flex items-center gap-1.5"><Network size={13} />Network</span>} pad={false}>
            <div className="p-4 pb-2"><Spark values={s.map((x: any) => (x.net_rx_bps === null ? null : x.net_rx_bps / 1e3))} label="Inbound" fmt={(v) => `${v.toFixed(1)} kB/s`} /></div>
            <Table head={["Host", "Req", "In", "p50", "Err", "304"]}>
              {d.network.hosts.length ? d.network.hosts.slice(0, 8).map((x: any) => <tr key={x.host}>
                <td className="max-w-[9rem] truncate text-[12px]" title={x.host}>{x.host}{d.network.paused_hosts[x.host] ? <span className="ml-1 text-warning">paused {d.network.paused_hosts[x.host]}s</span> : null}</td>
                <td className="num">{x.requests}</td><td className="num">{mb(x.bytes_in)}</td><td className="num">{x.p50_ms ?? "—"}</td><td className="num">{x.errors + (x.status["4xx"] ?? 0) + (x.status["5xx"] ?? 0)}</td><td className="num">{x.not_modified}</td></tr>)
                : <tr><td colSpan={6} className="text-ink-3">no outbound requests since start</td></tr>}
            </Table>
          </Card>
          <Card title={<span className="inline-flex items-center gap-1.5"><Wallet size={13} />Economics (today)</span>}>
            <div className="grid grid-cols-2 gap-y-1 text-[12.5px]">
              <span className="text-ink-3">External API cost</span><span className="num">{usd(d.economics.today.external_cost_usd)}</span>
              <span className="text-ink-3">Local energy (est.)</span><span className="num">{d.economics.today.energy_wh?.toFixed(2)} Wh ≈ {usd(d.economics.today.local_energy_cost_usd_estimate)}</span>
              <span className="text-ink-3">Tokens</span><span className="num">{((d.economics.today.input_tokens ?? 0) + (d.economics.today.output_tokens ?? 0)).toLocaleString()}</span>
              <span className="text-ink-3">Savings actual / est.</span><span className="num">{usd(d.economics.savings.actual_usd)} / {usd(d.economics.savings.estimated_usd)}</span>
              <span className="text-ink-3">Month forecast</span><span className="num">{usd(d.economics.forecast.projected_month_usd, 2)}</span>
              <span className="text-ink-3">Limits</span><span className="num">day {d.economics.limits.daily_usd ?? "default"} · month {d.economics.limits.monthly_usd ?? "—"}</span>
            </div>
          </Card>
          <Card title={<span className="inline-flex items-center gap-1.5"><Gauge size={13} />Efficiency</span>} pad={false}>
            <div className="grid grid-cols-2 gap-y-1 p-4 text-[12.5px]">
              <span className="text-ink-3">Model calls (24 h)</span><span className="num">{d.efficiency.model_calls_24h}</span>
              <span className="text-ink-3">Avg tokens / call</span><span className="num">{d.efficiency.avg_tokens_per_call ?? "—"}</span>
              <span className="text-ink-3">Avg model latency</span><span className="num">{d.efficiency.avg_model_latency_ms ? `${d.efficiency.avg_model_latency_ms} ms` : "—"}</span>
              <span className="text-ink-3">Energy / successful task</span><span className="num">{d.efficiency.energy_wh_per_successful_task_estimate ?? "—"} Wh (est.)</span>
              <span className="text-ink-3">Response-cache hits (24 h)</span><span className="num">{d.efficiency.response_cache_hits_24h}</span>
              <span className="text-ink-3">Answer cache L2 / L3</span><span className="num">{d.efficiency.semantic_cache.l2_hits} / {d.efficiency.semantic_cache.l3_hits} hits · {d.efficiency.semantic_cache.misses} misses</span>
              <span className="text-ink-3">Archive index</span><span className="num">{!d.archive_index?.enabled ? "off (scan)" : d.archive_index.rows === 0 && d.archive_index.builds === 0 ? "not built yet (first search builds it)" : `${d.archive_index.live_rows} chunks · ${(d.archive_index.bytes / 1048576).toFixed(1)} MB · last refresh ${d.archive_index.last_build_ms ?? "—"} ms`}</span>
            </div>
            <Table head={["L1 cache", "Hit rate", "Hits", "Size"]}>
              {d.efficiency.l1_caches.filter((c: any) => c.hits !== undefined).map((c: any) => <tr key={c.name}><td className="text-[12px]">{c.name}</td>
                <td className="num">{c.hit_rate === null ? "—" : pct(c.hit_rate)}</td><td className="num">{c.hits}/{c.hits + c.misses}</td><td className="num">{c.size}/{c.maxsize}</td></tr>)}
            </Table>
          </Card>
          <Card title="Events" pad={false}>
            {d.events.length ? <ul className="max-h-72 divide-y divide-line/60 overflow-auto">{d.events.map((e: any, i: number) => <li key={i} className="px-4 py-1.5 text-[12px]">
              <span className="font-mono text-[11px] text-ink-3">{new Date(e.ts * 1000).toLocaleTimeString()}</span> <span className="text-ink-2">{e.kind.replaceAll("_", " ")}</span>{" "}
              <span className="text-ink-3">{Object.entries(e).filter(([k]) => !["ts", "kind"].includes(k)).map(([k, v]) => `${k}=${typeof v === "object" ? JSON.stringify(v) : v}`).join(" · ")}</span></li>)}</ul>
              : <div className="p-4 text-[12.5px] text-ink-3">No events yet.</div>}
          </Card>
        </div>
        <Card title="API routes — measured since start" className="mt-4" pad={false} action={<span className="text-[11px] text-ink-3">sorted by total time</span>}>
          {routes.data?.routes?.length ? <Table head={["Route", "Calls", "p50", "p95", "SQL / req", "Avg bytes", "5xx"]}>
            {routes.data.routes.map((r: any) => <tr key={r.route}><td className="font-mono text-[11.5px]">{r.route}</td><td className="num">{r.count}</td>
              <td className="num">{r.p50_ms} ms</td><td className="num">{r.p95_ms} ms</td><td className={`num ${r.sql_per_request > 25 ? "text-warning" : ""}`}>{r.sql_per_request}</td>
              <td className="num">{mb(r.avg_bytes)}</td><td className="num">{r.errors}</td></tr>)}
          </Table> : <div className="p-4"><Empty title="No requests measured yet" /></div>}
        </Card>
        <AskPanel />
      </>}
    </>
  );
}

function AskPanel() {
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);
  const [res, setRes] = useState<any>(null);
  const [plan, setPlan] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);
  const preview = async () => { setErr(null); try { setPlan(await api("/api/ai/plan", { method: "POST", json: { question: q } })); } catch (e) { setErr((e as Error).message); } };
  const ask = async () => { setBusy(true); setErr(null); setRes(null); try { setRes(await api("/api/ai/ask", { method: "POST", json: { question: q } })); } catch (e) { setErr((e as Error).message); } finally { setBusy(false); } };
  const p = res?.plan ?? plan?.plan;
  const c = res?.classification ?? plan?.classification;
  return (
    <Card title="Ask DAEMON — cheapest reliable strategy first" className="mt-4">
      <label className="sr-only" htmlFor="ask-q">Question</label>
      <textarea id="ask-q" rows={2} className="w-full" placeholder="e.g. 25% of 480 · What does our archive say about the Babylonian exile? · Latest research on LLM quantization" value={q} onChange={(e) => setQ(e.target.value)} />
      <div className="mt-2 flex flex-wrap gap-2"><Button onClick={preview} disabled={q.trim().length < 2}>Show plan (no cost)</Button><Button variant="primary" busy={busy} disabled={q.trim().length < 2} onClick={ask}>Ask</Button></div>
      <ErrorBanner error={err} />
      {p && <div className="mt-3 rounded border border-line bg-bg/60 p-3 text-[12.5px]">
        <div><span className="text-ink-3">Category</span> <span className="font-mono">{c?.category}</span> · <span className="text-ink-3">current info</span> {c?.needs_current_info ? "yes" : "no"} · <span className="text-ink-3">complexity</span> {c?.complexity}</div>
        <div><span className="text-ink-3">Strategy</span> <span className="font-mono text-violet">{p.strategy}</span>{p.research_depth ? ` (${p.research_depth})` : ""} — {p.reason}</div>
        {p.rejected?.length > 0 && <div className="text-ink-3">Rejected: {p.rejected.join(" · ")}</div>}
      </div>}
      {res && <div className="mt-3 space-y-2">
        <div className="text-[11.5px] text-ink-3">{res.latency_ms} ms · model calls {res.model_calls ?? 0} · {usd(res.cost_usd ?? 0)}{res.cached ? ` · served from ${res.cache_layer}` : ""}{res.model ? ` · ${res.provider}:${res.model}` : ""}</div>
        <div className="whitespace-pre-wrap font-serif text-[15px] text-ink">{res.answer ?? res.note ?? "No answer."}</div>
        {res.evidence_class && <div className="text-[11.5px] text-ink-3">{res.evidence_class}{res.method ? ` — ${res.method}` : ""}</div>}
        {(res.sources ?? []).length > 0 && <ol className="list-decimal space-y-0.5 pl-5 text-[12px] text-ink-2">{res.sources.slice(0, 8).map((s: any, i: number) => <li key={i}>
          {s.url ? <a className="text-violet hover:underline" href={s.url} target="_blank" rel="noreferrer">{s.title || s.url}</a> : <span>{s.title ?? s.document_title ?? s.ref}</span>}
          {s.source && <span className="text-ink-3"> · {s.source} · {s.reliability}{s.published_at ? ` · ${String(s.published_at).slice(0, 10)}` : ""}</span>}</li>)}</ol>}
      </div>}
    </Card>
  );
}
