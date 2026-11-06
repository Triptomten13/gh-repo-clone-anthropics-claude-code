"use client";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { Button, Card, Empty, ErrorBanner, PageHeader, StatusBadge, Table } from "@/components/ui";
import { useDialog } from "@/components/dialog";
import { ago, api, sek } from "@/lib/api";
import { useApi, useMe, useRefreshOn } from "@/lib/hooks";

const LEVEL = ["research", "analysis", "drafting", "internal ops", "external publishing", "financial / contractual"];
const FILTERS: [string, string][] = [["pending", "Waiting"], ["approved", "Approved"], ["rejected", "Rejected"], ["revoked", "Revoked"], ["", "All"]];

/** Where an approval comes from, so the decision can be checked against the thing it governs. */
function origin(a: any): { href: string; label: string } | null {
  const act: string = a.action ?? "";
  if (act.startsWith("tool:") || act.startsWith("archive.")) return { href: "/governance#tools", label: "Tool security" };
  const gov: Record<string, [string, string]> = { "policy.": ["policies", "Policies"], "audit.": ["audit", "Audit"], "budget.": ["budgets", "Budgets"],
    "tools.": ["tools", "Tool security"], "gates.": ["gates", "Evaluation gates"], "deploy.": ["deployment", "Deployment"] };
  for (const [prefix, [tab, label]] of Object.entries(gov)) if (act.startsWith(prefix)) return { href: `/governance#${tab}`, label };
  if (act.startsWith("knowledge.")) return { href: "/knowledge#documents", label: "The Archive" };
  if (act.startsWith("creative.")) return { href: "/creative", label: "Creative Center" };
  if (act.startsWith("providers.")) return { href: "/creative#providers", label: "Providers" };
  if (a.payload?.task_id) return { href: `/agents?task=${a.payload.task_id}`, label: `Task #${a.payload.task_id}` };
  return null;
}

/** Governance changes are applied from here once approved (the server repeats the stored request with every check). */
const APPLICABLE = new Set(["policy.write", "audit.prune", "tools.grant", "knowledge.declassify", "budget.change", "deploy.loosen_egress", "gates.change"]);

/** Lifecycle as one honest word: an approval can be approved and still authorise nothing (expired, revoked, used). */
function lifecycle(a: any): string {
  if (a.revoked_at) return "revoked";
  if (a.consumed_at) return "used";
  if (a.status === "approved" && a.expires_at && new Date(a.expires_at) < new Date()) return "expired";
  return a.status;
}

function Approvals() {
  const params = useSearchParams();
  const focus = Number(params.get("id")) || null;
  const [filter, setFilter] = useState(focus ? "" : "pending");
  const ap = useApi<any[]>(`/api/approvals${filter ? `?status=${filter}` : ""}`, [filter]);
  useRefreshOn(["approval"], ap.reload);
  const me = useMe();
  const canDecide = me?.permissions?.includes("approval.decide");
  const approvers = useApi<any[]>(canDecide ? "/api/approvals/approvers" : null, [canDecide]);
  const dlg = useDialog();
  const [notes, setNotes] = useState<Record<number, string>>({});
  const [delegateTo, setDelegateTo] = useState<Record<number, string>>({});
  const [busy, setBusy] = useState<number | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);
  useEffect(() => { if (focus && ap.data) document.getElementById(`approval-${focus}`)?.scrollIntoView({ block: "center" }); }, [focus, ap.data]);

  const run = async (id: number, what: string, f: () => Promise<unknown>) => {
    setBusy(id); setErr(null); setDone(null);
    try { await f(); setDone(`#${id} ${what}.`); ap.reload(); } catch (e) { setErr((e as Error).message); } finally { setBusy(null); }
  };
  const decide = (id: number, approve: boolean) =>
    run(id, approve ? "approved" : "rejected", () => api(`/api/approvals/${id}/decide`, { method: "POST", json: { approve, note: notes[id] ?? "" } }));
  const delegate = (id: number) =>
    run(id, `delegated to ${delegateTo[id]}`, () => api(`/api/approvals/${id}/delegate`, { method: "POST", json: { to: delegateTo[id] } }));
  const apply = (id: number) => run(id, "applied", () => api(`/api/approvals/${id}/apply`, { method: "POST" }));
  const revoke = async (id: number) => {
    const reason = await dlg.prompt({ title: `Revoke approval #${id}?`, label: "Reason (kept in the audit trail)",
      message: "The approved action will no longer be allowed to run. An action that has already run cannot be undone by revoking.", confirmLabel: "Revoke", danger: true });
    if (reason === null) return;
    await run(id, "revoked", () => api(`/api/approvals/${id}/revoke?reason=${encodeURIComponent(reason)}`, { method: "POST" }));
  };

  return (
    <>
      <PageHeader kicker="Approval center" title="Human control over consequential actions">
        <div role="group" aria-label="Show approvals" className="flex flex-wrap gap-1">
          {FILTERS.map(([v, l]) => <button key={l} aria-pressed={filter === v} onClick={() => setFilter(v)}
            className={`rounded-md border px-2.5 py-1 text-[12.5px] ${filter === v ? "border-violet text-ink" : "border-line text-ink-3 hover:text-ink-2"}`}>{l}</button>)}
        </div>
      </PageHeader>
      <ErrorBanner error={err || ap.error} />
      {done && <p role="status" className="mb-3 text-[13px] text-good">{done}</p>}
      <p className="mb-4 max-w-3xl text-[13px] text-ink-3">
        Purchases, supplier agreements, launches, ad budgets, live price changes, public content, governance changes and
        restricted data operations stop here. Agents can request; people with the approver permission decide — never the
        person who asked. An approval is bound to the exact request, expires, is used once, and can be revoked until it is used.
        Every step is in the audit trail.
      </p>
      <Card pad={false}>
        {ap.data?.length ? (
          <Table head={["Request", "Level", "Amount", "Requested by", "State", "When", "Decision"]} label="Approvals">
            {ap.data.map((a) => {
              const state = lifecycle(a);
              const from = origin(a);
              return (
                <tr key={a.id} id={`approval-${a.id}`} className={`align-top ${a.id === focus ? "bg-surface-2" : ""}`}>
                  <td className="min-w-[16rem]">
                    <div className="font-medium"><span className="font-mono text-[12px] text-violet">#{a.id}</span> {a.title}</div>
                    <div className="font-mono text-[11.5px] text-ink-3">{a.action}{from && <> · <Link className="text-violet underline underline-offset-2" href={from.href}>{from.label}</Link></>}</div>
                    <details className="max-w-lg"><summary className="cursor-pointer text-[12px] text-ink-3">details</summary>
                      <pre className="whitespace-pre-wrap text-[12px] text-ink-2">{a.description}</pre></details>
                  </td>
                  <td><span className={`text-[12px] ${a.level >= 5 ? "text-[#f08a8a]" : "text-warning"}`}>L{a.level} · {LEVEL[a.level] ?? a.category}</span></td>
                  <td className="num">{a.amount_sek ? sek(a.amount_sek) : "—"}</td>
                  <td className="text-ink-2">{a.requested_by}{a.on_behalf_of && <div className="text-[11px] text-ink-3">for {a.on_behalf_of}</div>}</td>
                  <td>
                    <StatusBadge status={state === "used" ? "completed" : state} />
                    <div className="mt-1 space-y-0.5 text-[11px] text-ink-3">
                      {a.delegated_to && <div>delegated to {a.delegated_to}</div>}
                      {a.decided_by && <div>{a.decided_by}{a.decision_note && `: ${a.decision_note}`}</div>}
                      {a.revoked_by && <div>revoked by {a.revoked_by} {ago(a.revoked_at)}</div>}
                      {a.consumed_at && <div>used {ago(a.consumed_at)}</div>}
                      {a.expires_at && !a.consumed_at && !a.revoked_at && <div>{state === "expired" ? "expired" : "expires"} {ago(a.expires_at)}</div>}
                    </div>
                  </td>
                  <td className="text-ink-3">{ago(a.created_at)}</td>
                  <td className="min-w-[13rem]">
                    {canDecide && a.status === "pending" && !a.revoked_at && (
                      <div className="flex flex-col gap-1.5">
                        <input aria-label={`Note for approval ${a.id}`} placeholder="note" value={notes[a.id] ?? ""} onChange={(e) => setNotes({ ...notes, [a.id]: e.target.value })} />
                        <div className="flex gap-1.5">
                          <Button variant="primary" busy={busy === a.id} onClick={() => decide(a.id, true)}>Approve</Button>
                          <Button variant="danger" busy={busy === a.id} onClick={() => decide(a.id, false)}>Reject</Button>
                        </div>
                        {!!approvers.data?.length && (
                          <div className="flex gap-1.5">
                            <select aria-label={`Delegate approval ${a.id} to`} value={delegateTo[a.id] ?? ""} onChange={(e) => setDelegateTo({ ...delegateTo, [a.id]: e.target.value })}>
                              <option value="">delegate to…</option>
                              {approvers.data.map((u) => <option key={u.email} value={u.email}>{u.email} ({u.role})</option>)}
                            </select>
                            <Button disabled={!delegateTo[a.id]} busy={busy === a.id} onClick={() => delegate(a.id)}>Delegate</Button>
                          </div>
                        )}
                      </div>
                    )}
                    {state === "approved" && APPLICABLE.has(a.action) && (
                      <div className="mb-1.5"><Button variant="primary" busy={busy === a.id} onClick={() => apply(a.id)}>Apply change</Button></div>
                    )}
                    {canDecide && (state === "approved" || (a.status === "pending" && !a.revoked_at)) && (
                      <div className="mt-1.5"><Button busy={busy === a.id} onClick={() => revoke(a.id)}>Revoke</Button></div>
                    )}
                    {!canDecide && a.status === "pending" && <span className="text-[12px] text-ink-3">waiting for an approver</span>}
                  </td>
                </tr>
              );
            })}
          </Table>
        ) : <div className="p-4"><Empty title={filter === "pending" ? "Nothing waiting for you" : "No approvals"} /></div>}
      </Card>
    </>
  );
}

export default function ApprovalsPage() {
  return <Suspense><Approvals /></Suspense>;
}
