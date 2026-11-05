"use client";
import { useEffect, useState } from "react";
import { Button, Card, ErrorBanner, Field, PageHeader, StatusBadge, Table } from "@/components/ui";
import { ago, api } from "@/lib/api";
import { label } from "@/lib/flare";
import { useApi } from "@/lib/hooks";

const STYLES = ["systematic", "cynical", "curious", "skeptical", "imaginative", "practical", "terse", "warm", "technical", "scholarly", "decisive"];
const NAMING = ["minimal", "mythic", "latin", "single", "nordic"];

export default function PersonasPage() {
  const [division, setDivision] = useState("");
  const list = useApi<any[]>(`/api/flare/personas${division ? `?division=${division}` : ""}`, [division]);
  const genres = useApi<any>("/api/flare/genres");
  const [sel, setSel] = useState<string>("the_accountant");
  const detail = useApi<any>(sel ? `/api/flare/personas/${sel}` : null, [sel]);
  const [draft, setDraft] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);
  const [saved, setSaved] = useState<string | null>(null);
  useEffect(() => { if (detail.data) setDraft(JSON.parse(JSON.stringify(detail.data))); }, [detail.data]);

  const save = async () => {
    const body: any = {};
    for (const k of ["personality", "decision_philosophy", "communication_style", "naming_style", "novelty_appetite", "risk_tolerance", "evaluation_lens", "genre_affinities", "creative_specialization", "known_biases", "expertise", "active"]) body[k] = draft[k];
    try { await api(`/api/flare/personas/${sel}`, { method: "PATCH", json: body }); setSaved(`Saved v${detail.data.version + 1}`); detail.reload(); list.reload(); setErr(null); }
    catch (e) { setErr((e as Error).message); }
  };
  const reset = async () => { try { await api(`/api/flare/personas/${sel}/reset`, { method: "POST" }); detail.reload(); setSaved("Reset to seed"); } catch (e) { setErr((e as Error).message); } };
  const divisions = Array.from(new Set((list.data ?? []).map((p) => p.division)));

  return (
    <>
      <PageHeader kicker="Rocky Flare · personality registry" title="Agent personalities">
        <select value={division} onChange={(e) => setDivision(e.target.value)}><option value="">all divisions</option>{["executive", "research", "opportunity", "brand", "marketing", "operations", "creative_studio", "commercial", "field_ops"].map((d) => <option key={d}>{d}</option>)}</select>
      </PageHeader>
      <ErrorBanner error={err} />
      <p className="mb-4 max-w-3xl text-[13px] text-ink-3">Personalities shape judgement — evaluation lens, genre affinities, novelty and risk appetite change scores and concepts measurably. They never carry permissions or budgets; those stay in the Agent Control Room. Every edit is versioned and audited.</p>
      <div className="grid gap-4 xl:grid-cols-[360px_1fr]">
        <Card title={`${list.data?.length ?? "…"} personalities`} pad={false}>
          <ul className="max-h-[760px] divide-y divide-line/60 overflow-auto">
            {(list.data ?? []).map((p) => (
              <li key={p.id}><button onClick={() => setSel(p.id)} className={`w-full px-4 py-2.5 text-left ${sel === p.id ? "bg-surface-2" : "hover:bg-surface-2/50"}`}>
                <div className="flex items-center justify-between"><span className="text-[13px] font-medium">{p.name}</span><span className="font-mono text-[10px] text-ink-3">{p.division}</span></div>
                <div className="truncate text-[11.5px] text-ink-3">{p.personality}</div>
                <div className="mt-0.5 text-[11px] text-ink-3">{p.metrics.tasks} tasks · {p.metrics.evaluations} reviews · {p.metrics.competition_wins} wins · v{p.version}</div>
              </button></li>
            ))}
          </ul>
          {divisions.length === 0 && null}
        </Card>
        {draft && (
          <div className="space-y-4">
            <Card title={`${draft.name} — ${draft.role}`} action={<span className="flex items-center gap-2 text-[12px] text-ink-3">agent <code>{draft.agent_id}</code> · level {draft.metrics.permission_level} · <StatusBadge status={draft.metrics.agent_status ?? "active"} /></span>}>
              <div className="grid gap-3 md:grid-cols-2">
                <Field label="Personality"><textarea rows={3} value={draft.personality} onChange={(e) => setDraft({ ...draft, personality: e.target.value })} /></Field>
                <Field label="Decision philosophy"><textarea rows={3} value={draft.decision_philosophy} onChange={(e) => setDraft({ ...draft, decision_philosophy: e.target.value })} /></Field>
                <Field label="Communication style"><select value={draft.communication_style} onChange={(e) => setDraft({ ...draft, communication_style: e.target.value })}>{STYLES.map((s) => <option key={s}>{s}</option>)}</select></Field>
                <Field label="Naming style"><select value={draft.naming_style} onChange={(e) => setDraft({ ...draft, naming_style: e.target.value })}>{NAMING.map((s) => <option key={s}>{s}</option>)}</select></Field>
                <Field label={`Novelty appetite · ${draft.novelty_appetite.toFixed(2)}`}><input type="range" min={0} max={1} step={0.05} value={draft.novelty_appetite} onChange={(e) => setDraft({ ...draft, novelty_appetite: Number(e.target.value) })} /></Field>
                <Field label={`Risk tolerance · ${draft.risk_tolerance.toFixed(2)}`}><input type="range" min={0} max={1} step={0.05} value={draft.risk_tolerance} onChange={(e) => setDraft({ ...draft, risk_tolerance: Number(e.target.value) })} /></Field>
                <Field label="Known biases (comma separated)"><input value={draft.known_biases.join(", ")} onChange={(e) => setDraft({ ...draft, known_biases: e.target.value.split(",").map((x) => x.trim()).filter(Boolean) })} /></Field>
                <Field label="Expertise (comma separated)"><input value={draft.expertise.join(", ")} onChange={(e) => setDraft({ ...draft, expertise: e.target.value.split(",").map((x) => x.trim()).filter(Boolean) })} /></Field>
              </div>
              <div className="mt-4 grid gap-4 md:grid-cols-2">
                <div>
                  <div className="mb-1.5 font-mono text-[10.5px] uppercase tracking-[0.14em] text-ink-3">Evaluation lens (weights)</div>
                  {detail.data.criteria.map((c: string) => (
                    <div key={c} className="flex items-center gap-2 text-[12px]">
                      <span className="w-36 text-ink-2">{label(c)}</span>
                      <input type="range" min={0} max={0.6} step={0.05} className="flex-1" value={draft.evaluation_lens[c] ?? 0}
                        onChange={(e) => setDraft({ ...draft, evaluation_lens: { ...draft.evaluation_lens, [c]: Number(e.target.value) } })} />
                      <span className="num w-10 text-right text-ink-3">{(draft.evaluation_lens[c] ?? 0).toFixed(2)}</span>
                    </div>
                  ))}
                </div>
                <div>
                  <div className="mb-1.5 font-mono text-[10.5px] uppercase tracking-[0.14em] text-ink-3">Genre affinities</div>
                  <div className="flex max-h-56 flex-wrap gap-1.5 overflow-auto">
                    {(genres.data?.genres ?? []).map((g: any) => {
                      const on = g.id in draft.genre_affinities;
                      return <button key={g.id} onClick={() => { const a = { ...draft.genre_affinities }; on ? delete a[g.id] : (a[g.id] = 1); setDraft({ ...draft, genre_affinities: a }); }}
                        className={`rounded border px-2 py-0.5 text-[11.5px] ${on ? "border-ember text-ember" : "border-line-strong text-ink-3 hover:text-ink-2"}`}>{g.name}</button>;
                    })}
                  </div>
                </div>
              </div>
              <div className="mt-4 flex items-center gap-2">
                <Button variant="primary" onClick={save}>Save new version</Button><Button onClick={reset}>Reset to seed</Button>
                <label className="ml-2 flex items-center gap-1.5 text-[12px] text-ink-3"><input type="checkbox" checked={draft.active} onChange={(e) => setDraft({ ...draft, active: e.target.checked })} /> active</label>
                {saved && <span className="text-[12px] text-good">{saved}</span>}
              </div>
            </Card>
            <div className="grid gap-4 md:grid-cols-2">
              <Card title="Performance metrics">
                <dl className="grid grid-cols-2 gap-y-1 text-[13px]">
                  <dt className="text-ink-3">Tasks</dt><dd className="num">{draft.metrics.tasks}</dd>
                  <dt className="text-ink-3">Success rate</dt><dd className="num">{draft.metrics.success_rate ?? "—"}</dd>
                  <dt className="text-ink-3">Reviews given</dt><dd className="num">{draft.metrics.evaluations}</dd>
                  <dt className="text-ink-3">Competition wins</dt><dd className="num">{draft.metrics.competition_wins}</dd>
                  <dt className="text-ink-3">Calibration</dt><dd className="num">{draft.metrics.calibration.correlation ?? `— (${draft.metrics.calibration.points} pts)`}</dd>
                  <dt className="text-ink-3">AI cost</dt><dd className="num">${draft.metrics.cost_usd}</dd>
                </dl>
                <p className="mt-2 text-[11.5px] text-ink-3">Calibration = correlation between this persona's concept scores and realised campaign profit (needs ≥3 points).</p>
              </Card>
              <Card title="Version history" pad={false}>
                <Table head={["v", "By", "When"]}>{detail.data.versions.map((v: any) => <tr key={v.id}><td className="num">{v.version}</td><td className="text-ink-2">{v.changed_by}</td><td className="text-ink-3">{ago(v.created_at)}</td></tr>)}</Table>
              </Card>
            </div>
          </div>
        )}
      </div>
    </>
  );
}
