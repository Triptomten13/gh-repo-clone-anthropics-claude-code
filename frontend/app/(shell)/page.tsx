"use client";
import Link from "next/link";
import { RevenueProfitChart } from "@/components/charts";
import { Card, DemoBadge, Empty, ErrorBanner, PageHeader, ScoreBar, Stat, StatusBadge } from "@/components/ui";
import { ago, fmt, sek } from "@/lib/api";
import { useApi, useRefreshOn } from "@/lib/hooks";

type Overview = {
  finance: { revenue: number; gross_profit: number; net_profit: number; contribution_margin: number; ad_spend: number; roas: number | null; entries: number; contains_demo_data: boolean };
  counts: Record<string, number>;
  top_products: { id: number; name: string; score: number; confidence: number; compliance: string; is_demo: boolean }[];
  emerging_trends: { keyword: string; stage: string; velocity_score: number; platforms: string[]; is_demo: boolean }[];
  alerts: { agent: string; kind: string; summary: string; at: string }[];
  llm_provider: string;
};

export default function OverviewPage() {
  const ov = useApi<Overview>("/api/overview");
  const fin = useApi<{ daily: any[] }>("/api/finance/summary?days=60");
  useRefreshOn(["task", "approval"], () => { ov.reload(); fin.reload(); });
  const d = ov.data;
  return (
    <>
      <PageHeader kicker="Executive overview" title="Operating picture" />
      <ErrorBanner error={ov.error} />
      {d && (
        <>
          {d.finance.contains_demo_data && (
            <div className="mb-4 rounded-md border border-violet-dim bg-violet/5 px-3 py-2 text-[12.5px] text-ink-2">
              Financials include <b className="text-violet">synthetic demo data</b>. Remove it under Systems &amp; Integrations before relying on these figures.
            </div>
          )}
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4 xl:grid-cols-6">
            <Stat label="Revenue" value={sek(d.finance.revenue)} sub={`${d.finance.entries} ledger entries`} />
            <Stat label="Net profit" value={sek(d.finance.net_profit)} accent sub={`ROAS ${fmt(d.finance.roas, 2)}`} />
            <Stat label="Active businesses" value={d.counts.active_businesses} sub="live stores" />
            <Stat label="Under investigation" value={d.counts.under_investigation} sub={`${d.counts.products} products tracked`} />
            <Stat label="Active experiments" value={d.counts.active_experiments} />
            <Stat label="Pending approvals" value={<Link href="/approvals" className="hover:underline">{d.counts.pending_approvals}</Link>} sub={`${d.counts.queued_tasks} tasks in queue`} />
          </div>

          <div className="mt-4 grid gap-4 xl:grid-cols-3">
            <Card title="Revenue & profit · last 60 days" className="xl:col-span-2">
              {fin.data?.daily?.length ? <RevenueProfitChart data={fin.data.daily} /> :
                <Empty title="No ledger data yet">Connect a payment provider or import ledger entries. Figures are only ever computed from recorded transactions.</Empty>}
            </Card>
            <Card title="Emerging & exploding trends" action={<Link className="text-[12px] text-violet hover:underline" href="/radar">Radar →</Link>}>
              {d.emerging_trends.length ? (
                <ul className="space-y-2.5">
                  {d.emerging_trends.map((t) => (
                    <li key={t.keyword} className="flex items-center justify-between gap-2 text-[13px]">
                      <span>{t.keyword}<DemoBadge show={t.is_demo} /><span className="ml-2 text-[11px] text-ink-3">{t.platforms.join(" · ")}</span></span>
                      <span className="flex items-center gap-2"><StatusBadge status={t.stage} /><span className="num w-8 text-right">{t.velocity_score.toFixed(0)}</span></span>
                    </li>
                  ))}
                </ul>
              ) : <Empty title="No emerging trends detected">Add keywords to the watchlist and run a market scan.</Empty>}
            </Card>
          </div>

          <div className="mt-4 grid gap-4 xl:grid-cols-2">
            <Card title="Best opportunities" action={<Link className="text-[12px] text-violet hover:underline" href="/lab">Laboratory →</Link>}>
              {d.top_products.length ? (
                <ul className="divide-y divide-line/60">
                  {d.top_products.map((p) => (
                    <li key={p.id} className="flex items-center justify-between gap-3 py-2 text-[13px]">
                      <Link href={`/lab/${p.id}`} className="truncate hover:text-violet">{p.name}<DemoBadge show={p.is_demo} /></Link>
                      <span className="flex items-center gap-3"><StatusBadge status={p.compliance} /><ScoreBar score={p.score} confidence={p.confidence} /></span>
                    </li>
                  ))}
                </ul>
              ) : <Empty title="No scored products">Import products or run research, then evaluate them.</Empty>}
            </Card>
            <Card title="Operational alerts · 24h">
              {d.alerts.length ? (
                <ul className="space-y-2">
                  {d.alerts.map((a, i) => (
                    <li key={i} className="flex gap-2 text-[12.5px]">
                      <StatusBadge status={a.kind === "error" ? "failed" : "blocked"} />
                      <span className="text-ink-3">{a.agent}</span>
                      <span className="flex-1 truncate text-ink-2" title={a.summary}>{a.summary}</span>
                      <span className="whitespace-nowrap text-ink-3">{ago(a.at)}</span>
                    </li>
                  ))}
                </ul>
              ) : <Empty title="All clear">No failed or blocked agent tasks in the last 24 hours.</Empty>}
            </Card>
          </div>
        </>
      )}
    </>
  );
}
