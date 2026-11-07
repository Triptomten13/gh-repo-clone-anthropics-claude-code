"use client";
import { useState } from "react";
import { VelocityBars } from "@/components/charts";
import { Button, Card, DemoBadge, Empty, ErrorBanner, PageHeader, StatusBadge, Table } from "@/components/ui";
import { ago, api, fmt } from "@/lib/api";
import { useApi, useRefreshOn } from "@/lib/hooks";

type Trend = { id: number; keyword: string; stage: string; velocity_score: number; growth_rate: number; acceleration: number; platforms: string[]; observations: number; confidence: number; is_demo: boolean; updated_at: string };

export default function RadarPage() {
  const trends = useApi<Trend[]>("/api/trends");
  const watch = useApi<{ keywords: string[] }>("/api/watchlist");
  const [kw, setKw] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  useRefreshOn(["task"], trends.reload);

  const run = async (type: string, payload = {}) => {
    setBusy(type); setErr(null);
    try { const t = await api("/api/tasks", { method: "POST", json: { type, payload, force: true } }); setNotice(`Task #${t.id} (${type}) queued — follow it in the Agent Control Room.`); }
    catch (e) { setErr((e as Error).message); } finally { setBusy(null); }
  };
  const saveWatch = async (keywords: string[]) => {
    try { watch.setData(await api("/api/watchlist", { method: "PUT", json: { keywords } })); } catch (e) { setErr((e as Error).message); }
  };
  const list = trends.data ?? [];
  const multi = list.filter((t) => t.platforms.length >= 2 && ["emerging", "exploding"].includes(t.stage));

  return (
    <>
      <PageHeader kicker="Market radar" title="Trend intelligence">
        <Button busy={busy === "intel.scan_market"} onClick={() => run("intel.scan_market")} variant="primary">Run market scan</Button>
        <Button busy={busy === "trend.analyze"} onClick={() => run("trend.analyze")}>Re-analyse trends</Button>
      </PageHeader>
      <ErrorBanner error={err || trends.error} />
      {notice && <div className="mb-4 rounded-md border border-line bg-surface px-3 py-2 text-[12.5px] text-ink-2">{notice}</div>}

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
        <Card title="Watchlist" className="xl:col-span-1">
          <form className="mb-3 flex gap-2" onSubmit={(e) => { e.preventDefault(); if (kw.trim()) { saveWatch([...(watch.data?.keywords ?? []), kw]); setKw(""); } }}>
            <input className="flex-1" placeholder="add keyword, e.g. sourdough" value={kw} onChange={(e) => setKw(e.target.value)} />
            <Button type="submit">Add</Button>
          </form>
          <div className="flex flex-wrap gap-1.5">
            {(watch.data?.keywords ?? []).map((k) => (
              <button key={k} title="remove" onClick={() => saveWatch(watch.data!.keywords.filter((x) => x !== k))}
                className="rounded border border-line-strong px-2 py-0.5 text-[12px] text-ink-2 hover:border-critical/60 hover:text-[#f08a8a]">{k} ×</button>
            ))}
            {!watch.data?.keywords?.length && <span className="text-[12.5px] text-ink-3">The daily scan researches these keywords on every configured platform.</span>}
          </div>
          <div className="mt-5 border-t border-line pt-3">
            <div className="mb-2 font-mono text-[10.5px] uppercase tracking-[0.14em] text-ink-3">Cross-platform signals</div>
            {multi.length ? multi.map((t) => (
              <div key={t.id} className="flex justify-between py-1 text-[13px]"><span>{t.keyword}<DemoBadge show={t.is_demo} /></span><span className="text-ink-3">{t.platforms.join(" · ")}</span></div>
            )) : <div className="text-[12.5px] text-ink-3">No trend is growing independently on 2+ platforms yet.</div>}
          </div>
        </Card>
        <Card title="Trend velocity (0–100)" className="xl:col-span-2">
          {list.length ? <VelocityBars data={list.slice(0, 15)} /> : <Empty title="No trends yet">Trends are computed from observations collected by research agents or imported datasets.</Empty>}
        </Card>
      </div>

      <Card title="All trends" className="mt-4" pad={false}>
        {list.length ? (
          <Table head={["Keyword", "Stage", "Velocity", "Weekly growth", "Acceleration", "Platforms", "Obs.", "Confidence", "Updated"]}>
            {list.map((t) => (
              <tr key={t.id}>
                <td className="font-medium">{t.keyword}<DemoBadge show={t.is_demo} /></td>
                <td><StatusBadge status={t.stage} /></td>
                <td className="num">{fmt(t.velocity_score)}</td>
                <td className="num">{(t.growth_rate * 100).toFixed(1)}%</td>
                <td className="num">{(t.acceleration * 100).toFixed(1)}%</td>
                <td className="text-ink-2">{t.platforms.join(", ")}</td>
                <td className="num">{t.observations}</td>
                <td className="num">{(t.confidence * 100).toFixed(0)}%</td>
                <td className="text-ink-3">{ago(t.updated_at)}</td>
              </tr>
            ))}
          </Table>
        ) : <div className="p-4"><Empty title="Nothing to show" /></div>}
      </Card>
    </>
  );
}
