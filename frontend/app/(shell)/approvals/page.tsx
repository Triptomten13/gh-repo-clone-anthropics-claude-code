"use client";
import { useState } from "react";
import { Button, Card, Empty, ErrorBanner, PageHeader, StatusBadge, Table } from "@/components/ui";
import { ago, api, sek } from "@/lib/api";
import { useApi, useRefreshOn } from "@/lib/hooks";

const LEVEL = ["research", "analysis", "drafting", "internal ops", "external publishing", "financial / contractual"];

export default function ApprovalsPage() {
  const [filter, setFilter] = useState("pending");
  const ap = useApi<any[]>(`/api/approvals${filter ? `?status=${filter}` : ""}`, [filter]);
  useRefreshOn(["approval"], ap.reload);
  const [notes, setNotes] = useState<Record<number, string>>({});
  const [err, setErr] = useState<string | null>(null);
  const decide = async (id: number, approve: boolean) => {
    try { await api(`/api/approvals/${id}/decide`, { method: "POST", json: { approve, note: notes[id] ?? "" } }); ap.reload(); } catch (e) { setErr((e as Error).message); }
  };
  return (
    <>
      <PageHeader kicker="Approval center" title="Human control over consequential actions">
        <select value={filter} onChange={(e) => setFilter(e.target.value)}><option value="pending">pending</option><option value="approved">approved</option><option value="rejected">rejected</option><option value="">all</option></select>
      </PageHeader>
      <ErrorBanner error={err || ap.error} />
      <p className="mb-4 max-w-3xl text-[13px] text-ink-3">
        Purchases, supplier agreements, launches, ad budgets, live price changes, public content and customer messages all stop here.
        Agents can request; only an admin can decide. Every decision is written to the audit trail.
      </p>
      <Card pad={false}>
        {ap.data?.length ? (
          <Table head={["Request", "Action", "Level", "Amount", "Requested by", "Status", "When", "Decision"]}>
            {ap.data.map((a) => (
              <tr key={a.id} className="align-top">
                <td><div className="font-medium">{a.title}</div><details className="max-w-lg"><summary className="cursor-pointer text-[12px] text-ink-3">details</summary><pre className="whitespace-pre-wrap text-[12px] text-ink-2">{a.description}</pre></details></td>
                <td className="font-mono text-[12px]">{a.action}</td>
                <td><span className={`text-[12px] ${a.level >= 5 ? "text-[#f08a8a]" : "text-warning"}`}>L{a.level} · {LEVEL[a.level]}</span></td>
                <td className="num">{a.amount_sek ? sek(a.amount_sek) : "—"}</td>
                <td className="text-ink-2">{a.requested_by}</td>
                <td><StatusBadge status={a.status} />{a.decided_by && <div className="mt-1 text-[11px] text-ink-3">{a.decided_by}{a.decision_note && `: ${a.decision_note}`}</div>}</td>
                <td className="text-ink-3">{ago(a.created_at)}</td>
                <td>{a.status === "pending" && (
                  <div className="flex flex-col gap-1.5">
                    <input placeholder="note" value={notes[a.id] ?? ""} onChange={(e) => setNotes({ ...notes, [a.id]: e.target.value })} />
                    <div className="flex gap-1.5"><Button variant="primary" onClick={() => decide(a.id, true)}>Approve</Button><Button variant="danger" onClick={() => decide(a.id, false)}>Reject</Button></div>
                  </div>
                )}</td>
              </tr>
            ))}
          </Table>
        ) : <div className="p-4"><Empty title={filter === "pending" ? "Nothing waiting for you" : "No approvals"} /></div>}
      </Card>
    </>
  );
}
