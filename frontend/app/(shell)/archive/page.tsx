"use client";
import { useState } from "react";
import { Card, Empty, ErrorBanner, PageHeader, Table } from "@/components/ui";
import { ago } from "@/lib/api";
import { useApi } from "@/lib/hooks";

export default function ArchivePage() {
  const audit = useApi<any[]>("/api/audit?limit=500");
  const lessons = useApi<any[]>("/api/lessons");
  const suppliers = useApi<any[]>("/api/suppliers");
  const [q, setQ] = useState("");
  const match = (o: unknown) => !q || JSON.stringify(o).toLowerCase().includes(q.toLowerCase());
  return (
    <>
      <PageHeader kicker="Intelligence archive" title="Decisions, lessons & audit trail">
        <input placeholder="search everything…" value={q} onChange={(e) => setQ(e.target.value)} className="w-72" />
      </PageHeader>
      <ErrorBanner error={audit.error} />
      <div className="grid gap-4 xl:grid-cols-2">
        <Card title="Lessons learned">
          {lessons.data?.filter(match).length ? <ul className="space-y-2 text-[13px]">{lessons.data.filter(match).map((l) => <li key={l.id}><span className="text-ink-3">{l.source} · {ago(l.created_at)}</span><div className="text-ink-2">{l.text}</div></li>)}</ul>
            : <Empty title="No lessons yet">Completed and abandoned experiments write their lessons here.</Empty>}
        </Card>
        <Card title="Suppliers" pad={false}>
          {suppliers.data?.filter(match).length ? (
            <Table head={["Supplier", "Country", "Rating", "MOQ", "Delivery", "Reliability"]}>
              {suppliers.data.filter(match).map((s) => <tr key={s.id}><td>{s.name}{s.is_demo && <span className="ml-1 text-[10px] text-ember">DEMO</span>}</td><td>{s.country}{s.eu_based && " (EU)"}</td><td className="num">{s.rating ?? "—"}</td><td className="num">{s.moq ?? "—"}</td><td className="num">{s.avg_delivery_days ?? "—"}d</td><td className="num">{s.reliability_score ?? "—"}</td></tr>)}
            </Table>
          ) : <div className="p-4"><Empty title="No suppliers" /></div>}
        </Card>
      </div>
      <Card title="Audit trail" className="mt-4" pad={false}>
        <Table head={["When", "Actor", "Action", "Target", "Details"]}>
          {(audit.data ?? []).filter(match).map((a) => (
            <tr key={a.id}><td className="whitespace-nowrap text-ink-3">{ago(a.created_at)}</td><td className="text-ink-2">{a.actor}</td><td className="font-mono text-[12px]">{a.action}</td>
              <td className="text-ink-2">{a.target}</td><td className="max-w-xl truncate font-mono text-[11px] text-ink-3" title={JSON.stringify(a.details)}>{JSON.stringify(a.details)}</td></tr>
          ))}
        </Table>
      </Card>
    </>
  );
}
