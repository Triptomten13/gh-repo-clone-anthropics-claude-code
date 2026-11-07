"use client";
import { useState } from "react";
import { GraphView, ProductPicker, Swatches } from "@/components/flare";
import { Button, Card, Empty, ErrorBanner, Json, PageHeader } from "@/components/ui";
import { label, useRun } from "@/lib/flare";
import { useApi } from "@/lib/hooks";

export default function ThinkSideways() {
  const meta = useApi<any>("/api/flare/challenges");
  const [pid, setPid] = useState<number | null>(null);
  const [q, setQ] = useState("What else could we do with this product?");
  const [useLlm, setUseLlm] = useState(false);
  const [res, setRes] = useState<any>(null);
  const [graph, setGraph] = useState<any>(null);
  const { run, busy, error } = useRun();
  const status = useApi<any>("/api/system/status");
  const ask = async () => {
    const t = await run("flare.sideways", { product_id: pid, question: q, use_llm: useLlm });
    if (t?.result) { setRes(t.result); setGraph(await (await import("@/lib/api")).api(`/api/flare/graphs/sideways:${pid}`)); }
  };
  const challenge = async (id: string) => { const t = await run("flare.sideways", { challenge_id: id, product_id: pid }); if (t?.result) { setRes(t.result); setGraph(null); } };
  const byCat: Record<string, any[]> = {};
  for (const i of res?.items ?? []) (byCat[i.category] ??= []).push(i);
  return (
    <>
      <PageHeader kicker="Rocky Flare · unexpected opportunity engine" title="Think Sideways" />
      <ErrorBanner error={error} />
      <Card className="mb-4">
        <div className="flex flex-wrap items-end gap-2">
          <ProductPicker value={pid} onChange={setPid} />
          <input className="w-full flex-1 sm:w-auto sm:min-w-96" value={q} onChange={(e) => setQ(e.target.value)} />
          <label className="flex items-center gap-1.5 text-[12px] text-ink-3" title={status.data?.llm_provider === "none" ? "No AI provider configured — the task will be blocked" : ""}>
            <input type="checkbox" checked={useLlm} onChange={(e) => setUseLlm(e.target.checked)} /> add AI ideas {status.data?.llm_provider === "none" && "(not configured)"}</label>
          <Button variant="primary" disabled={!pid} busy={busy === "flare.sideways"} onClick={ask}>Think sideways</Button>
        </div>
        <div className="mt-3 flex flex-wrap gap-1.5">{(meta.data?.questions ?? []).map((x: string) => <button key={x} onClick={() => setQ(x)} className="rounded border border-line-strong px-2 py-0.5 text-[12px] text-ink-3 hover:text-ink">{x}</button>)}</div>
      </Card>
      <Card title="Field Operations challenges" className="mb-4">
        <div className="grid grid-cols-1 gap-1.5 md:grid-cols-2">{(meta.data?.challenges ?? []).map((c: any) => <button key={c.id} onClick={() => challenge(c.id)} className="rounded-md border border-line bg-bg/50 px-3 py-2 text-left text-[12.5px] hover:border-gold">{c.text}<span className="ml-1 break-all font-mono text-[10px] text-ink-3">{c.engine}</span></button>)}</div>
      </Card>
      {!res ? <Card><Empty title="Ask a question or pick a challenge">Results are hypotheses with a named bridge — validate demand before investing.</Empty></Card> : (
        <>
          {res.domains && (
            <div className="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
              <Card title={`Cross-industry graph · mode: ${res.mode}`}>{graph?.nodes?.length ? <GraphView nodes={graph.nodes} edges={graph.edges} height={460} /> : <Empty title="No graph" />}</Card>
              <Card title="Highest-potential combinations">
                {res.high_potential.map((c: any, i: number) => (
                  <div key={i} className="mb-3 rounded-md border border-line bg-bg/50 p-3">
                    <div className="flex justify-between text-[13px] font-medium"><span>{c.title}</span><span className="num text-violet">{c.potential}</span></div>
                    <div className="text-[12px] text-ink-2">{c.customer_group} · via {c.channel}</div>
                    <div className="text-[11.5px] text-ink-3">{c.reasoning.join(" · ")}</div>
                  </div>
                ))}
                <p className="text-[11.5px] text-ink-3">{res.note}</p>
              </Card>
            </div>
          )}
          {Object.keys(byCat).length > 0 && (
            <div className="mt-4 grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-4">
              {Object.entries(byCat).map(([cat, items]) => (
                <Card key={cat} title={`5 × ${cat}`}>
                  <ul className="space-y-1.5">{items.map((i, k) => <li key={k} className="text-[12.5px]"><span className="text-ink">{i.text}</span><div className="text-[11px] text-ink-3">{label(i.domain)} · bridge: {i.bridge}</div></li>)}</ul>
                </Card>
              ))}
            </div>
          )}
          {res.identities && <Card title="Three radically different identities" className="mt-4"><div className="grid grid-cols-1 gap-2 md:grid-cols-3">{res.identities.map((d: any) => <div key={d.hybrid_id} className="rounded-md border border-line p-3"><b>{d.title}</b><div className="my-1"><Swatches colors={d.brand_system.color_palette} /></div><div className="text-[12px] text-ink-3">{d.brand_system.primary_genre} × {d.brand_system.secondary_genre}</div></div>)}</div></Card>}
          {res.llm && <Card title="AI ideas (hypotheses)" className="mt-4"><ul className="space-y-1.5 text-[12.5px]">{res.llm.ideas.map((x: any, i: number) => <li key={i}><b>{x.title}</b> — {x.description} <span className="text-ink-3">(bridge: {x.bridge}; validate: {x.how_to_validate})</span></li>)}</ul></Card>}
          {(res.ecosystems || res.hybrid || res.candidates || res.products || res.opportunities || res.uncommon_models || res.audience_monetization) && <Card title="Engine output" className="mt-4"><Json value={{ ...res, items: undefined, graph_edges: undefined }} /></Card>}
        </>
      )}
    </>
  );
}
