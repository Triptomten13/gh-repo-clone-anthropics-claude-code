"use client";
import { useState } from "react";
import { GraphView, ProductPicker } from "@/components/flare";
import { Button, Card, Empty, Epistemic, ErrorBanner, PageHeader, Table } from "@/components/ui";
import { label, useRun } from "@/lib/flare";
import { useApi } from "@/lib/hooks";

const STATUS_STYLE: Record<string, string> = { existing_product: "text-ember", supplier_customization: "text-[#5fd35f]", proposed_modification: "text-series-1", original_concept: "text-[#b4acf0]" };

export default function MutationLab() {
  const [pid, setPid] = useState<number | null>(null);
  const g = useApi<any>(pid ? `/api/flare/graphs/mutation:${pid}` : null, [pid]);
  const inn = useApi<any>(pid ? `/api/field/innovation/${pid}` : null, [pid]);
  const eco = useApi<any>("/api/field/ecosystems");
  const { run, busy, error } = useRun();
  const mutate = async () => { await run("flare.mutate", { product_id: pid }); g.reload(); };
  const nodes = (inn.data?.mutations ?? []) as any[];
  return (
    <>
      <PageHeader kicker="Rocky Flare · mutation lab" title="Product Mutation Engine 2.0">
        <ProductPicker value={pid} onChange={setPid} />
        <Button variant="primary" disabled={!pid} busy={busy === "flare.mutate"} onClick={mutate}>Run mutation engine & save graph</Button>
      </PageHeader>
      <ErrorBanner error={error} />
      <div className="mb-4 flex flex-wrap gap-4 text-[12px]">{Object.entries(STATUS_STYLE).map(([k, v]) => <span key={k} className={v}>● {label(k)}</span>)}<span className="text-ink-3">— conceptual modifications are never presented as manufactured products</span></div>
      {!pid ? <Card><Empty title="Pick a product" /></Card> : (
        <>
          <div className="grid gap-4 xl:grid-cols-2">
            <Card title="Mutation graph">
              {g.data?.nodes?.length ? <GraphView nodes={g.data.nodes} edges={g.data.edges} /> : <Empty title="No saved graph yet">Run the mutation engine to persist the graph.</Empty>}
            </Card>
            <Card title="Ranked mutations" pad={false}>
              <Table head={["Mutation", "Status", "Value", "Cost", "Cmplx", "Diff", "Profit", "Reg. risk", "Rank"]}>
                {nodes.map((n) => (
                  <tr key={n.key} title={[n.concept, ...n.reasoning, ...n.verification_needed.map((v: string) => "verify: " + v)].join("\n")}>
                    <td className="min-w-40"><div className="font-medium capitalize">{label(n.mutation_type)}</div><div className="max-w-56 truncate text-[11px] text-ink-3">{n.concept}</div></td>
                    <td className={`text-[11.5px] ${STATUS_STYLE[n.status]}`}>{label(n.status)}</td>
                    {["customer_value", "cost", "complexity", "differentiation", "profit_potential"].map((k) => <td key={k} className="num">{n[k]}</td>)}
                    <td className={`num ${n.regulatory_risk >= 4 ? "text-[#f08a8a]" : n.regulatory_risk >= 3 ? "text-warning" : ""}`}>{n.regulatory_risk}</td>
                    <td className="num">{n.rank_score}</td>
                  </tr>
                ))}
              </Table>
            </Card>
          </div>
          <div className="mt-4 grid gap-4 xl:grid-cols-2">
            <Card title="Survival & outdoor innovation lab" pad={false}>
              <Table head={["Question", "Proposal", "Status", "Verification before any claim"]}>
                {(inn.data?.innovation ?? []).map((i: any) => (
                  <tr key={i.key}><td className="text-ink-2">{i.question}</td><td className="text-[12px]">{i.proposal}</td>
                    <td className="text-[11.5px] text-ink-3">{label(i.status)} <Epistemic kind={i.epistemic} /></td><td className="text-[12px] text-ink-3">{i.verification}</td></tr>
                ))}
              </Table>
            </Card>
            <Card title="Modular ecosystems (catalogue coverage)">
              {(eco.data?.ecosystems ?? []).map((e: any) => (
                <div key={e.template} className="mb-3">
                  <div className="text-[13px] font-medium">{e.label} <span className="num text-ink-3">{Math.round(e.coverage * 100)}% covered</span></div>
                  <div className="mt-1 flex flex-wrap gap-1.5">{e.modules.map((m: any) => <span key={m.id} title={m.products.map((p: any) => p.name).join(", ")}
                    className={`rounded border px-2 py-0.5 text-[11.5px] ${m.products.length ? "border-good/40 text-[#5fd35f]" : "border-dashed border-line-strong text-ink-3"}`}>{m.label}</span>)}</div>
                </div>
              ))}
              <p className="text-[11.5px] text-ink-3">{eco.data?.ecosystems?.[0]?.note}</p>
            </Card>
          </div>
        </>
      )}
    </>
  );
}
