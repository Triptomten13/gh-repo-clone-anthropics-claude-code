"use client";
import Link from "next/link";
import { useState } from "react";
import { Card, Empty, ErrorBanner, Json, PageHeader, StatusBadge, Table } from "@/components/ui";
import { ago } from "@/lib/api";
import { useApi, useRefreshOn } from "@/lib/hooks";
import { useIdentity } from "@/lib/identity";

const LINKS: Record<string, [string, string][]> = {
  executive: [["G-sus Chamber", "/chamber"], ["Approval Center", "/approvals"]], research: [["Market Radar", "/radar"], ["Field Operations", "/field"]],
  development: [["Systems & Integrations", "/settings"]], archive: [["The Archive", "/knowledge"], ["Archivum", "/archivum"]],
  creative: [["Brand Laboratory", "/flare/brands"], ["Creative Intelligence", "/flare"]], operations: [["Agent Registry", "/agents"]],
  security: [["Audit & Lessons", "/archive"], ["Approval Center", "/approvals"]], laboratory: [["AI Core", "/ai"], ["Experiment Lab", "/experiments"]],
};

function headline(d: any): string {
  const m = d.metrics ?? {};
  switch (d.id) {
    case "executive": return `${m.pending_approvals} approvals pending · ${m.gsus_runs} G-sus runs`;
    case "archive": return `${m.documents} documents · ${m.canon_chapters} canon chapters · ${m.canon_contradictions} contradictions`;
    case "creative": return `${m.concepts} concepts · ${m.assets} assets`;
    case "operations": return `${m.queued_tasks} tasks in queue · scheduler ${m.scheduler_enabled ? "on" : "off"}`;
    case "security": return `${m.failed_logins_24h} failed logins · ${m.lockouts_24h} lockouts · ${m.injection_flagged_documents} flagged docs (24h)`;
    case "laboratory": return m.last_eval ? `last eval ${m.last_eval.ran_at}` : "no evaluations run yet";
    default: return `${d.agents.length} agents`;
  }
}

export default function HQ() {
  const identity = useIdentity();
  const depts = useApi<any[]>("/api/hq/departments");
  useRefreshOn(["task", "approval", "kill_switch"], depts.reload);
  const [sel, setSel] = useState<string | null>(null);
  const d = depts.data?.find((x) => x.id === sel);
  return (
    <>
      <PageHeader kicker={`${identity.company_name} · infrastructure`} title="Demonkoncernen HQ" />
      <ErrorBanner error={depts.error} />
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        {(depts.data ?? []).map((x) => (
          <button key={x.id} onClick={() => setSel(x.id)} aria-pressed={sel === x.id}
            className={`rounded-lg border p-4 text-left transition ${sel === x.id ? "border-cyan bg-cyan/5" : "border-line bg-surface hover:border-line-strong"}`}>
            <div className="flex items-start justify-between gap-2"><span className="font-serif text-[16px] text-ink">{x.title}</span><StatusBadge status={x.status === "nominal" ? "active" : "pending"} /></div>
            <div className="mt-1 text-[12px] text-ink-3">{x.purpose}</div>
            <div className="mt-3 text-[12.5px] text-ink-2">{headline(x)}</div>
            <div className="mt-1 text-[11.5px] text-ink-3">{x.agents.length} agents{x.alerts.length ? ` · ${x.alerts.length} alerts (24h)` : ""}</div>
          </button>
        ))}
      </div>
      {d ? (
        <div className="mt-4 grid gap-4 xl:grid-cols-3">
          <Card title={`${d.title} · agents`} pad={false}>
            {d.agents.length ? <Table head={["Agent", "Status", "Lvl", "OK/blk/fail", "$"]}>{d.agents.map((a: any) => <tr key={a.id}><td className="text-[12.5px]">{a.name}</td><td><StatusBadge status={a.status} /></td><td className="num">{a.level}</td><td className="num">{a.ok}/{a.blocked}/{a.failed}</td><td className="num">{a.cost_usd}</td></tr>)}</Table>
              : <div className="p-4 text-[12.5px] text-ink-3">This department has no runtime agents; its work is shown in the metrics.</div>}
          </Card>
          <Card title="Recent work & alerts">
            {d.alerts.length > 0 && <ul className="mb-3 space-y-1">{d.alerts.map((a: any) => <li key={a.task_id} className="text-[12px]"><StatusBadge status={a.status} /> <span className="font-mono">{a.type}</span> <span className="text-ink-3">{a.error}</span></li>)}</ul>}
            {d.recent_tasks.length ? <ul className="space-y-1">{d.recent_tasks.map((t: any) => <li key={t.id} className="flex items-center gap-2 text-[12px]"><StatusBadge status={t.status} /><span className="font-mono">{t.type}</span><span className="text-ink-3">{t.agent} · {ago(t.created_at)}</span></li>)}</ul>
              : <Empty title="No recent work" />}
          </Card>
          <Card title="Metrics & links">
            <div className="mb-3 flex flex-wrap gap-2">{(LINKS[d.id] ?? []).map(([l, h]) => <Link key={h} href={h} className="inline-flex min-h-7 items-center rounded border border-line px-2.5 py-1 text-[12px] text-cyan hover:border-cyan pointer-coarse:min-h-9">{l} →</Link>)}</div>
            <Json value={d.metrics} />
          </Card>
        </div>
      ) : <Card className="mt-4"><Empty title="Select a department">Every number here is read live from the database — nothing is staged.</Empty></Card>}
    </>
  );
}
