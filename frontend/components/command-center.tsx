"use client";
/** What needs attention across the organisation, and whether the system is operational — from GET /api/attention,
 *  computed from stored records at request time. Every item links to the place where it is handled. */
import { AlertTriangle, CheckCircle2, Info, OctagonAlert, Hand } from "lucide-react";
import Link from "next/link";
import { Card, ErrorBanner, StatusBadge } from "@/components/ui";
import { ago } from "@/lib/api";
import { useApi, useRefreshOn } from "@/lib/hooks";

type Item = { severity: "critical" | "action" | "warning" | "info"; title: string; detail: string; href: string; count: number | null };
type Attention = {
  generated_at: string; attention: Item[];
  status: { kill_switch: boolean; offline_mode: boolean; agents: number; agents_active: number; agents_suspended: number; tasks_running: number; tasks_queued: number;
    tasks_done_24h: number; approvals_pending: number; cost_today_usd: number; daily_cost_limit_usd: number;
    models_today: { provider: string; model: string; calls: number }[]; providers: { provider: string; locality: string; configured: boolean; state: string }[] };
};

const SEV = {
  critical: { icon: OctagonAlert, cls: "border-critical/60 text-[#f08a8a]", label: "Critical" },
  action: { icon: Hand, cls: "border-violet/60 text-violet", label: "Your action" },
  warning: { icon: AlertTriangle, cls: "border-warning/50 text-warning", label: "Warning" },
  info: { icon: Info, cls: "border-line-strong text-ink-2", label: "For information" },
};

export function CommandCenter() {
  const a = useApi<Attention>("/api/attention");
  useRefreshOn(["task", "approval", "kill_switch"], a.reload);
  const s = a.data?.status;
  return (
    <div className="mb-4 grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
      <Card title="Needs attention" action={a.data && <span className="text-[11px] text-ink-3">checked {ago(a.data.generated_at)}</span>} pad={false}>
        <ErrorBanner error={a.error} />
        {!a.data && !a.error && <p className="p-4 text-[13px] text-ink-3">Checking approvals, agents, runs, providers and monitors…</p>}
        {a.data && (a.data.attention.length ? (
          <ul className="divide-y divide-line">
            {a.data.attention.map((it, i) => {
              const v = SEV[it.severity]; const Icon = v.icon;
              return (
                <li key={i}><Link href={it.href} className="flex items-start gap-3 px-4 py-3 hover:bg-surface-2">
                  <span className={`mt-0.5 inline-flex shrink-0 items-center gap-1 rounded border px-1.5 py-0.5 text-[10.5px] ${v.cls}`}><Icon size={12} aria-hidden />{v.label}</span>
                  <span className="min-w-0"><span className="block text-[13.5px] text-ink">{it.title}</span>{it.detail && <span className="block truncate text-[12px] text-ink-3">{it.detail}</span>}</span>
                </Link></li>
              );
            })}
          </ul>
        ) : <div className="flex items-center gap-2 p-4 text-[13px] text-ink-2"><CheckCircle2 size={16} className="text-good" aria-hidden />Nothing needs your attention: no waiting approvals, failures, failing providers or unreviewed changes.</div>)}
      </Card>
      <Card title="System">
        {s ? (
          <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-[12.5px]">
            <dt className="text-ink-3">State</dt><dd>{s.kill_switch ? <StatusBadge status="blocked" /> : <StatusBadge status="operational" />}{s.kill_switch && <span className="ml-1 text-[#f08a8a]">emergency stop</span>}{s.offline_mode && <span className="ml-1 text-ink-3">offline mode</span>}</dd>
            <dt className="text-ink-3">Agents</dt><dd><Link className="hover:underline" href="/agents">{s.agents_active} active of {s.agents}</Link>{s.agents_suspended ? <span className="text-ink-3"> · {s.agents_suspended} suspended</span> : null}</dd>
            <dt className="text-ink-3">Tasks</dt><dd>{s.tasks_running} running · {s.tasks_queued} queued · {s.tasks_done_24h} done in 24 h</dd>
            <dt className="text-ink-3">Approvals</dt><dd><Link className="hover:underline" href="/approvals">{s.approvals_pending} waiting</Link></dd>
            <dt className="text-ink-3">AI spend today</dt><dd className="num">${s.cost_today_usd.toFixed(2)} of ${s.daily_cost_limit_usd}</dd>
            <dt className="text-ink-3">Providers</dt><dd>{s.providers.filter((p) => p.configured).map((p) => `${p.provider}${p.state === "open" ? " (failing)" : ""}`).join(", ") || <span className="text-warning">none available</span>}</dd>
            <dt className="text-ink-3">Models today</dt><dd>{s.models_today.length ? s.models_today.map((m) => `${m.model} ×${m.calls}`).join(", ") : <span className="text-ink-3">no model calls yet</span>}</dd>
          </dl>
        ) : <p className="text-[13px] text-ink-3">{a.error ? "Unavailable." : "Loading…"}</p>}
      </Card>
    </div>
  );
}
