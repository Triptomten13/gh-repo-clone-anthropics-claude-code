"use client";
import { useState } from "react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { ProductPicker } from "@/components/flare";
import { Button, Card, Empty, ErrorBanner, Field, PageHeader, StatusBadge, Table } from "@/components/ui";
import { api, sek } from "@/lib/api";
import { label, useRun } from "@/lib/flare";
import { useApi, useRefreshOn } from "@/lib/hooks";

export default function CampaignStudio() {
  const [pid, setPid] = useState<number | null>(null);
  const camps = useApi<any[]>(`/api/flare/campaigns${pid ? `?product_id=${pid}` : ""}`, [pid]);
  const an = useApi<any>("/api/flare/campaigns/analysis");
  useRefreshOn(["task", "approval"], () => { camps.reload(); an.reload(); });
  const { run, busy, error, setError } = useRun();
  const [perfFor, setPerfFor] = useState<number | null>(null);
  const [perf, setPerf] = useState({ period_start: new Date().toISOString().slice(0, 10), impressions: "", clicks: "", engagements: "", spend: "", orders: "", revenue: "", contribution: "" });
  const submitPerf = async () => {
    const body: any = { period_start: perf.period_start + "T00:00:00Z" };
    for (const k of ["impressions", "clicks", "engagements", "orders"]) body[k] = Number((perf as any)[k] || 0);
    for (const k of ["spend", "revenue"]) body[k] = Number((perf as any)[k] || 0);
    if (perf.contribution) body.contribution = Number(perf.contribution);
    try { await api(`/api/flare/campaigns/${perfFor}/performance`, { method: "POST", json: [body] }); setPerfFor(null); an.reload(); } catch (e) { setError((e as Error).message); }
  };
  const launch = async (id: number) => { try { await api(`/api/flare/campaigns/${id}/request-launch`, { method: "POST" }); camps.reload(); } catch (e) { setError((e as Error).message); } };
  const rows = an.data?.campaigns ?? [];
  const chart = rows.slice(0, 10).map((r: any) => ({ name: r.name.split(" · ").slice(1).join(" · ") || r.name, contribution: r.contribution_after_ads, engagements: r.engagements }));

  return (
    <>
      <PageHeader kicker="Rocky Flare · campaign studio" title="Campaign identities, tests & what actually earns">
        <ProductPicker value={pid} onChange={setPid} />
        <Button variant="primary" disabled={!pid} busy={busy === "flare.campaign_matrix"} onClick={async () => { await run("flare.campaign_matrix", { product_id: pid }); camps.reload(); }}>Generate testing matrix</Button>
      </PageHeader>
      <ErrorBanner error={error || camps.error} />
      {an.data?.insight && <div className="mb-4 rounded-md border border-violet-dim bg-violet/5 px-3 py-2 text-[13px] text-ink-2">{an.data.insight}</div>}
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <Card title="Contribution after ads vs engagement (per campaign)">
          {chart.length ? (
            <div className="grid grid-cols-2 gap-2">
              {(["contribution", "engagements"] as const).map((k) => (
                <div key={k}>
                  <div className="mb-1 flex items-center gap-1.5 text-[11.5px] text-ink-2"><i className={`inline-block h-2 w-3 ${k === "contribution" ? "bg-series-3" : "bg-series-1"}`} />{k === "contribution" ? "Contribution after ads (SEK)" : "Engagements (likes, comments, shares)"}</div>
                  <ResponsiveContainer width="100%" height={240}>
                    <BarChart data={chart} layout="vertical" margin={{ left: 0, right: 30 }}>
                      <CartesianGrid stroke="#2e2d2a" horizontal={false} />
                      <XAxis type="number" stroke="#3d3c38" tick={{ fill: "#8c8b84", fontSize: 10 }} />
                      <YAxis type="category" dataKey="name" width={k === "contribution" ? 120 : 0} tick={{ fill: "#8c8b84", fontSize: 10 }} hide={k !== "contribution"} />
                      <Tooltip contentStyle={{ background: "#222220", border: "1px solid #3d3c38", fontSize: 12 }} cursor={{ fill: "#2e2d2a55" }} />
                      <Bar dataKey={k} fill={k === "contribution" ? "#199e70" : "#3987e5"} radius={[0, 4, 4, 0]} barSize={12} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              ))}
            </div>
          ) : <Empty title="No performance recorded yet">Record real results per campaign. The analyst ranks by contribution — never by likes.</Empty>}
        </Card>
        <Card title="Creative feature performance" pad={false}>
          {Object.keys(an.data?.features ?? {}).length ? (
            <Table head={["Feature", "Campaigns", "Spend", "Profit", "Profit / 100 kr"]}>
              {Object.entries(an.data.features).sort((a: any, b: any) => (b[1].profit_per_100_spend ?? -999) - (a[1].profit_per_100_spend ?? -999)).map(([k, v]: any) =>
                <tr key={k}><td>{label(k)}</td><td className="num">{v.campaigns}</td><td className="num">{sek(v.spend)}</td><td className="num">{sek(v.profit)}</td><td className="num">{v.profit_per_100_spend}</td></tr>)}
            </Table>
          ) : <div className="p-4"><Empty title="Nothing learned yet" /></div>}
        </Card>
      </div>
      {perfFor && (
        <Card title={`Record actual results · campaign #${perfFor}`} className="mt-4">
          <div className="grid grid-cols-2 gap-2 md:grid-cols-4 xl:grid-cols-8">
            {Object.keys(perf).map((k) => <Field key={k} label={label(k)}><input type={k === "period_start" ? "date" : "number"} value={(perf as any)[k]} onChange={(e) => setPerf({ ...perf, [k]: e.target.value })} /></Field>)}
          </div>
          <div className="mt-2 flex gap-2"><Button variant="primary" onClick={submitPerf}>Save & re-analyse</Button><Button onClick={() => setPerfFor(null)}>Cancel</Button></div>
          <p className="mt-1 text-[11.5px] text-ink-3">Contribution = revenue after COGS, fees and returns, before ad spend. Leave empty if unknown — it will be marked as estimated.</p>
        </Card>
      )}
      <Card title="Campaign matrix" className="mt-4" pad={false}>
        {camps.data?.length ? (
          <Table head={["Campaign", "Identity", "Platform", "Hook", "Video", "Test budget", "Status", ""]}>
            {camps.data.map((c) => (
              <tr key={c.id} className="align-top">
                <td className="max-w-56"><div className="font-medium">{c.name.split(" · ")[0]}</div><div className="text-[11px] text-ink-3">{label(c.genre)}</div></td>
                <td className="text-ink-2">{label(c.identity)}</td><td className="text-ink-2">{label(c.platform)}</td>
                <td className="max-w-72 text-[12px]">{c.hook}{c.flags?.length > 0 && <div className="text-warning">⚠ {c.flags.join("; ")}</div>}</td>
                <td className="text-[12px] text-ink-3">{c.video_format}</td><td className="num">{c.budget_recommendation_sek ? sek(c.budget_recommendation_sek) : "—"}</td>
                <td><StatusBadge status={c.status} /></td>
                <td className="space-x-1 whitespace-nowrap"><Button onClick={() => setPerfFor(c.id)}>Results</Button>{c.status === "draft" && <Button onClick={() => launch(c.id)} title="LEVEL 5 approval">Request launch</Button>}</td>
              </tr>
            ))}
          </Table>
        ) : <div className="p-4"><Empty title="No campaigns">Generate a testing matrix for a product or a concept.</Empty></div>}
      </Card>
    </>
  );
}
