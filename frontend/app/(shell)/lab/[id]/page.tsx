"use client";
import Link from "next/link";
import { use, useState } from "react";
import { ScoreComponents } from "@/components/charts";
import { Button, Card, DemoBadge, Empty, Epistemic, ErrorBanner, Field, Json, PageHeader, Stat, StatusBadge, Table } from "@/components/ui";
import { ago, api, fmt, pct, sek } from "@/lib/api";
import { useApi, useRefreshOn } from "@/lib/hooks";

export default function ProductPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const p = useApi<any>(`/api/products/${id}`, [id]);
  useRefreshOn(["task"], p.reload);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const task = async (type: string, payload: Record<string, unknown> = {}) => {
    setBusy(type); setErr(null);
    try { await api("/api/tasks", { method: "POST", json: { type, payload: { product_id: Number(id), ...payload }, force: true } }); }
    catch (e) { setErr((e as Error).message); } finally { setBusy(null); }
  };
  const evaluate = async () => {
    setBusy("eval");
    try { await api(`/api/products/${id}/evaluate`, { method: "POST" }); } catch (e) { setErr((e as Error).message); } finally { setBusy(null); }
  };

  const d = p.data;
  if (!d) return <ErrorBanner error={p.error} />;
  const opp = d.opportunities?.[0];
  const econTask = d.tasks.find((t: any) => t.type === "cfo.economics" && t.status === "succeeded");
  const econ = econTask?.result?.economics;
  const scen = econTask?.result?.pricing?.scenarios ?? {};
  const rep = d.compliance_report ?? {};
  const latest = (type: string) => d.tasks.find((t: any) => t.type === type);

  return (
    <>
      <div className="mb-2 text-[12px] text-ink-3"><Link href="/lab" className="hover:text-ink-2">← Product laboratory</Link></div>
      <PageHeader kicker={`${d.category || "uncategorised"} · ${d.source_platform}`} title={d.name}>
        <DemoBadge show={d.is_demo} />
        <Button variant="primary" busy={busy === "eval"} onClick={evaluate}>Run full evaluation</Button>
        <Button busy={busy === "opportunity.generate"} onClick={() => task("opportunity.generate", { enrich: true })} title="Requires an LLM provider">AI-enrich transformations</Button>
        <Button busy={busy === "brand.generate"} onClick={() => task("brand.generate")} title="Requires an LLM provider">Brand concepts</Button>
        <Button busy={busy === "content.generate"} onClick={() => task("content.generate", { channel: "tiktok" })} title="Requires an LLM provider">Content drafts</Button>
        <Button busy={busy === "ads.plan"} onClick={() => task("ads.plan")}>Ads plan</Button>
      </PageHeader>
      <ErrorBanner error={err} />
      <p className="mb-4 max-w-3xl text-[13.5px] text-ink-2">{d.description}</p>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        <Stat label="Opportunity score" value={d.opportunity_score?.toFixed(0) ?? "—"} accent sub={`data coverage ${pct(d.score_confidence)}`} />
        <Stat label="Gross margin" value={pct(d.gross_margin)} />
        <Stat label="Net margin" value={pct(d.net_margin)} sub="after assumed CAC" />
        <Stat label="Wholesale → retail" value={<span className="text-lg">{sek(d.wholesale_price)} → {sek(d.retail_price)}</span>} />
        <Stat label="Trend velocity" value={fmt(d.trend_velocity, 0)} sub={(d.platforms_seen ?? []).join(" · ") || "no linked trend"} />
        <Stat label="Compliance" value={<StatusBadge status={d.compliance_status} />} sub={d.status} />
      </div>

      <div className="mt-4 grid gap-4 xl:grid-cols-2">
        <Card title="Score composition">
          {d.score_breakdown?.components ? (
            <>
              <ScoreComponents components={d.score_breakdown.components} />
              <p className="mt-2 text-[11.5px] text-ink-3">Bar opacity = data coverage. Missing inputs score a neutral 50 and lower confidence rather than being guessed.</p>
              {d.score_breakdown.flags?.length > 0 && <ul className="mt-2 space-y-1 text-[12px] text-warning">{d.score_breakdown.flags.map((f: string) => <li key={f}>⚠ {f}</li>)}</ul>}
              <Adjustments pid={d.id} items={d.score_adjustments} onDone={p.reload} onError={setErr} />
            </>
          ) : <Empty title="Not scored yet">Run the full evaluation.</Empty>}
        </Card>
        <ComplianceCard d={d} rep={rep} onDone={p.reload} onError={setErr} />
      </div>

      <div className="mt-4 grid gap-4 xl:grid-cols-2">
        <Card title="Unit economics (per order, SEK)">
          {econ ? (
            <Table head={["Line", "Value"]}>
              {[["Retail price incl. VAT", econ.assumptions.retail_price_incl_vat], ["VAT", -econ.vat], ["Net revenue", econ.net_revenue], ["Landed cost (unit + freight + duty)", -econ.landed_cost],
                ["Gross profit", econ.gross_profit], ["Expected return cost", -econ.expected_return_cost], ["Contribution before ads", econ.contribution_before_ads],
                ["Break-even CAC", econ.break_even_cac], ["Break-even ROAS", econ.break_even_roas]].map(([k, v]) => (
                <tr key={k as string}><td className="text-ink-2">{k}</td><td className="num">{k === "Break-even ROAS" ? fmt(v as number, 2) : sek(v as number, 2)}</td></tr>
              ))}
            </Table>
          ) : <Empty title="No economics yet">{latest("cfo.economics")?.error ?? "Needs wholesale price and a retail or competitor price."}</Empty>}
        </Card>
        <Card title="Pricing scenarios">
          {Object.keys(scen).length ? (
            <Table head={["Scenario", "Price", "Contribution", "Margin", "Note"]}>
              {Object.entries(scen).map(([k, s]: any) => (
                <tr key={k}><td className="font-medium">{k}</td><td className="num">{sek(s.price)}</td><td className="num">{sek(s.contribution_margin, 0)}</td>
                  <td className="num">{pct(s.contribution_margin_pct)}</td><td className="max-w-80 text-[12px] text-ink-3">{s.rationale}</td></tr>
              ))}
            </Table>
          ) : <Empty title="No scenarios yet" />}
        </Card>
      </div>

      {opp && (
        <div className="mt-4 grid gap-4 xl:grid-cols-3">
          <Card title="Recommended business models">
            <ol className="space-y-3">
              {opp.business_models.map((m: any, i: number) => (
                <li key={m.model}>
                  <div className="flex justify-between text-[13.5px] font-medium"><span>{i + 1}. {m.model.replaceAll("_", " ")}</span><span className="num text-ember">{m.score}</span></div>
                  <ul className="mt-1 space-y-0.5 text-[12px] text-ink-3">{m.fit_reasons.map((r: string) => <li key={r}>{r}</li>)}</ul>
                </li>
              ))}
            </ol>
          </Card>
          <Card title={`Transformation lab · ${opp.transformations.length} concepts`} className="xl:col-span-2">
            <div className="grid gap-2 md:grid-cols-2">
              {opp.transformations.map((t: any, i: number) => (
                <div key={i} className="rounded-md border border-line bg-bg/60 p-3">
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-[13px] font-medium">{t.title}</span>
                    <span className="font-mono text-[10px] uppercase text-ink-3">{t.family.replace("_", " ")} · {t.effort}</span>
                  </div>
                  <p className="mt-1 text-[12.5px] text-ink-2">{t.concept}</p>
                  <div className="mt-1.5 flex items-center gap-2 text-[11px] text-ink-3"><Epistemic kind={t.epistemic} />{t.value_driver}{t.source === "llm" && " · AI"}</div>
                </div>
              ))}
            </div>
          </Card>
        </div>
      )}

      <Card title="Agent work on this product" className="mt-4" pad={false}>
        {d.tasks.length ? (
          <Table head={["#", "Task", "Agent", "Status", "When", "Result / reason"]}>
            {d.tasks.map((t: any) => (
              <tr key={t.id}>
                <td className="num text-ink-3">{t.id}</td><td className="font-mono text-[12px]">{t.type}</td><td className="text-ink-2">{t.agent_id}</td>
                <td><StatusBadge status={t.status} /></td><td className="text-ink-3">{ago(t.finished_at ?? t.created_at)}</td>
                <td className="max-w-xl text-[12px] text-ink-2">
                  {t.error ? <span className="text-ink-3">{t.error.split("\n")[0]}</span> : t.result ? <details><summary className="cursor-pointer text-ink-3">view output</summary><Json value={t.result} /></details> : "—"}
                </td>
              </tr>
            ))}
          </Table>
        ) : <div className="p-4"><Empty title="No agent work yet" /></div>}
      </Card>
    </>
  );
}

function ComplianceCard({ d, rep, onDone, onError }: { d: any; rep: any; onDone: () => void; onError: (e: string) => void }) {
  const [checked, setChecked] = useState<Record<string, boolean>>({});
  const [note, setNote] = useState("");
  const items: any[] = rep.checklist ?? [];
  const all = items.length > 0 && items.every((i) => checked[i.id]);
  const decide = async (approve: boolean) => {
    try { await api(`/api/products/${d.id}/compliance-decision`, { method: "POST", json: { approve, note, checklist_confirmed: all } }); onDone(); }
    catch (e) { onError((e as Error).message); }
  };
  return (
    <Card title="Compliance · Sweden / EU" action={<StatusBadge status={d.compliance_status} />}>
      {!items.length ? <Empty title="Not assessed">The Chief Risk Agent runs during evaluation.</Empty> : (
        <>
          {[...(rep.blockers ?? []).map((b: string) => ["blocked", b]), ...(rep.restrictions ?? []).map((b: string) => ["restricted", b]), ...(rep.warnings ?? []).map((b: string) => ["needs_review", b])].map(([s, b]) => (
            <div key={b} className="mb-1.5 flex items-start gap-2 text-[12.5px]"><StatusBadge status={s} /><span className="text-ink-2">{b}</span></div>
          ))}
          <ul className="mt-3 max-h-64 space-y-1 overflow-auto pr-1">
            {items.map((i) => (
              <li key={i.id}><label className="flex items-start gap-2 text-[12.5px] text-ink-2">
                <input type="checkbox" className="mt-0.5" checked={!!checked[i.id]} onChange={(e) => setChecked({ ...checked, [i.id]: e.target.checked })} />
                <span><span className="font-mono text-[10px] uppercase text-ink-3">{i.category}</span> {i.item}</span>
              </label></li>
            ))}
          </ul>
          {rep.human_decision && <div className="mt-2 text-[12px] text-ink-3">Human decision by {rep.human_decision.by}: “{rep.human_decision.note}”</div>}
          <div className="mt-3 flex flex-wrap items-end gap-2 border-t border-line pt-3">
            <Field label="Reviewer note (admin)"><input className="w-64" value={note} onChange={(e) => setNote(e.target.value)} /></Field>
            <Button variant="primary" disabled={!all || note.length < 3} onClick={() => decide(true)} title="Every checklist item must be verified">Approve for launch</Button>
            <Button variant="danger" disabled={note.length < 3} onClick={() => decide(false)}>Block</Button>
          </div>
          <p className="mt-2 text-[11px] text-ink-3">{rep.disclaimer}</p>
        </>
      )}
    </Card>
  );
}

function Adjustments({ pid, items, onDone, onError }: { pid: number; items: any[]; onDone: () => void; onError: (e: string) => void }) {
  const [delta, setDelta] = useState("");
  const [reason, setReason] = useState("");
  const add = async () => {
    try { await api(`/api/products/${pid}/adjustments`, { method: "POST", json: { delta: Number(delta), reason } }); setDelta(""); setReason(""); onDone(); }
    catch (e) { onError((e as Error).message); }
  };
  return (
    <div className="mt-3 border-t border-line pt-3">
      <div className="mb-1.5 font-mono text-[10.5px] uppercase tracking-[0.14em] text-ink-3">Audited score adjustments (±30, applied on next scoring)</div>
      {(items ?? []).map((a, i) => <div key={i} className="text-[12px] text-ink-2"><span className="num">{a.delta > 0 ? "+" : ""}{a.delta}</span> · {a.reason} <span className="text-ink-3">({a.by})</span></div>)}
      <div className="mt-2 flex gap-2">
        <input type="number" className="w-20" placeholder="±" value={delta} onChange={(e) => setDelta(e.target.value)} />
        <input className="flex-1" placeholder="reason (required)" value={reason} onChange={(e) => setReason(e.target.value)} />
        <Button disabled={!delta || reason.length < 3} onClick={add}>Add</Button>
      </div>
    </div>
  );
}
