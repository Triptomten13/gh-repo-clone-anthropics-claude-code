"use client";
import { useState } from "react";
import { Card, Empty, Epistemic, ErrorBanner, Json, PageHeader, Table } from "@/components/ui";
import { ago } from "@/lib/api";
import { useApi, useRefreshOn } from "@/lib/hooks";

const STANCE: Record<string, string> = { support: "text-[#5fd35f]", oppose: "text-[#f08a8a]", caution: "text-warning", propose: "text-series-1", decide: "text-violet", neutral: "text-ink-3" };

export default function CollabPage() {
  const [kind, setKind] = useState("");
  const sessions = useApi<any[]>(`/api/flare/sessions${kind ? `?kind=${kind}` : ""}`, [kind]);
  const [sel, setSel] = useState<number | null>(null);
  const s = useApi<any>(sel ? `/api/flare/sessions/${sel}` : null, [sel]);
  useRefreshOn(["task"], () => { sessions.reload(); s.reload(); });
  const d = s.data;
  return (
    <>
      <PageHeader kicker="Rocky Flare · agent collaboration" title="Collaboration log">
        <select value={kind} onChange={(e) => setKind(e.target.value)}><option value="">all kinds</option>{["discussion", "panel", "council", "competition"].map((k) => <option key={k}>{k}</option>)}</select>
      </PageHeader>
      <ErrorBanner error={sessions.error} />
      <div className="grid gap-4 xl:grid-cols-[340px_minmax(0,1fr)]">
        <Card title="Sessions" pad={false}>
          {sessions.data?.length ? (
            <ul className="max-h-[760px] divide-y divide-line/60 overflow-auto">
              {sessions.data.map((x) => (
                <li key={x.id}><button onClick={() => setSel(x.id)} className={`w-full px-4 py-2.5 text-left ${sel === x.id ? "bg-surface-2" : "hover:bg-surface-2/50"}`}>
                  <div className="flex justify-between text-[13px]"><span className="font-medium">#{x.id} {x.kind}</span><span className="text-ink-3">{x.status}</span></div>
                  <div className="text-[11.5px] text-ink-3">{x.topic} · {x.turns} turns · {ago(x.created_at)}</div>
                </button></li>
              ))}
            </ul>
          ) : <div className="p-4"><Empty title="No sessions">Start a discussion, panel, council or competition from the Brand Laboratory or Field Operations.</Empty></div>}
        </Card>
        {d ? (
          <div className="space-y-4">
            <Card title={`#${d.id} ${d.kind} · ${d.topic}`}>
              <ol className="space-y-3">
                {d.turns.map((t: any) => (
                  <li key={t.id} className="rounded-md border border-line bg-bg/50 p-3">
                    <div className="flex flex-wrap items-center gap-2 text-[12px]">
                      <b className="text-ink">{t.persona_name}</b><span className="font-mono text-[10.5px] text-ink-3">{t.seat}</span>
                      <span className={`font-mono text-[11px] uppercase ${STANCE[t.stance] ?? ""}`}>{t.stance}</span>
                      {t.scores?.weighted_score != null && <span className="num text-ink-2">score {t.scores.weighted_score}</span>}
                      <Epistemic kind={t.method === "llm" ? "hypothesis" : "estimate"} /><span className="text-ink-3">{t.method}</span>
                    </div>
                    <p className="mt-1.5 text-[13px] text-ink-2">{t.message}</p>
                  </li>
                ))}
              </ol>
            </Card>
            <Card title="Outcome (no forced consensus)">
              {d.decision?.ranking ? (
                <Table head={["Concept", "Mean", "Spread", "Verdict", "Stances", "Dissent"]}>
                  {d.decision.ranking.map((r: any) => (
                    <tr key={r.concept_id}><td className="font-medium">{r.name}{d.decision.shortlisted === r.concept_id && <span className="ml-1.5 text-[11px] text-violet">shortlisted</span>}</td>
                      <td className="num">{r.mean}</td><td className="num">±{r.stdev}</td><td className={r.consensus === "split" ? "text-warning" : "text-ink-2"}>{r.consensus}</td>
                      <td className="text-[12px] text-ink-3">{Object.entries(r.stances).map(([k, v]) => `${k} ${v}`).join(" · ")}</td>
                      <td className="text-[12px] text-ink-3">{r.dissent.map((x: any) => `${x.persona}: ${x.why}`).join(" | ") || "—"}</td></tr>
                  ))}
                </Table>
              ) : <Json value={d.decision} />}
              {d.decision?.council && <div className="mt-4"><div className="mb-1 font-mono text-[10.5px] uppercase tracking-[0.14em] text-gold">Council outputs</div><Json value={d.decision.council} /></div>}
            </Card>
          </div>
        ) : <Card><Empty title="Select a session" /></Card>}
      </div>
    </>
  );
}
