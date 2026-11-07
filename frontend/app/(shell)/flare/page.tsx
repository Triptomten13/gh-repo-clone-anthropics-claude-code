"use client";
import Link from "next/link";
import { useState } from "react";
import { Swatches } from "@/components/flare";
import { Button, Card, Empty, ErrorBanner, PageHeader, Stat, Table } from "@/components/ui";
import { api } from "@/lib/api";
import { label } from "@/lib/flare";
import { useApi, useRefreshOn } from "@/lib/hooks";

export default function CreativeIntelligence() {
  const genres = useApi<any>("/api/flare/genres");
  const personas = useApi<any[]>("/api/flare/personas");
  const concepts = useApi<any[]>("/api/flare/concepts");
  const dna = useApi<any>("/api/flare/style-dna");
  const evo = useApi<any>("/api/flare/genre-evolution");
  useRefreshOn(["task"], () => { concepts.reload(); genres.reload(); });
  const [family, setFamily] = useState("");
  const [picked, setPicked] = useState<string[]>([]);
  const [name, setName] = useState("");
  const [hybrid, setHybrid] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);
  const creative = (personas.data ?? []).filter((p) => ["creative_studio", "brand", "field_ops"].includes(p.division));
  const fuse = async () => {
    try { setHybrid(await api("/api/flare/genres/fuse", { method: "POST", json: { components: picked, name: name || undefined } })); genres.reload(); setErr(null); }
    catch (e) { setErr((e as Error).message); }
  };
  const list = (genres.data?.genres ?? []).filter((g: any) => !family || g.family === family);
  const recent = (concepts.data ?? []).slice(0, 12);

  return (
    <>
      <PageHeader kicker="Rocky Flare · creative intelligence" title="Creative instinct, measured" />
      <ErrorBanner error={err || genres.error} />
      <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
        <Stat label="Creative agents" value={creative.length} sub={`${personas.data?.length ?? "…"} personalities total`} />
        <Stat label="Genres in taxonomy" value={genres.data?.genres?.length ?? "…"} sub="incl. pillar D narratives" />
        <Stat label="Hybrids discovered" value={genres.data?.discovered?.length ?? "…"} sub="by fusion & users" />
        <Stat label="Brand concepts" value={concepts.data?.length ?? "…"} sub={`${(concepts.data ?? []).filter((c) => c.status === "needs_revision").length} need revision`} />
        <Stat label="Style DNA" value={<span className="text-lg">{dna.data?.status ?? "…"}</span>} sub={`${Object.keys(dna.data?.evidence ?? {}).length} learned features`} accent />
      </div>

      <div className="mt-4 grid grid-cols-1 gap-4 xl:grid-cols-3">
        <Card title="Hybrid fusion lab" className="xl:col-span-1">
          <p className="mb-2 text-[12.5px] text-ink-3">Pick 2–4 genres. Order matters: the first carries structure, the second the story.</p>
          <div className="mb-2 flex flex-wrap gap-1.5">{picked.map((g) => <button key={g} onClick={() => setPicked(picked.filter((x) => x !== g))} className="rounded border border-violet-dim px-2 py-0.5 text-[12px] text-violet">{label(g)} ×</button>)}</div>
          <div className="flex gap-2"><input placeholder="optional name" value={name} onChange={(e) => setName(e.target.value)} className="flex-1" /><Button variant="primary" disabled={picked.length < 2} onClick={fuse}>Fuse</Button></div>
          {hybrid && (
            <div className="mt-3 space-y-1.5 rounded-md border border-line bg-bg/60 p-3 text-[12.5px]">
              <div className="flex items-center justify-between"><b className="text-[14px]">{hybrid.name}</b>{hybrid.novel && <span className="text-[11px] text-violet">novel hybrid</span>}</div>
              <Swatches colors={hybrid.palette} />
              <div className="text-ink-2">{hybrid.concept}</div>
              <div className="text-ink-3"><b className="text-ink-2">Philosophy:</b> {hybrid.philosophy}</div>
              <div className="text-ink-3"><b className="text-ink-2">Type:</b> {hybrid.typography.display} / {hybrid.typography.text}</div>
              <div className="text-ink-3"><b className="text-ink-2">Materials:</b> {hybrid.materials.join(", ")} · {hybrid.surface_treatments.join(", ")}</div>
              <div className="text-ink-3"><b className="text-ink-2">Packaging:</b> {hybrid.packaging_direction}</div>
              <div className="text-ink-3"><b className="text-ink-2">Audience:</b> {hybrid.target_audience}</div>
              {[...hybrid.originality_flags, ...hybrid.trademark.hits.map((h: any) => ({ code: "trademark", detail: h.note }))].map((f: any, i: number) => <div key={i} className="text-warning">⚠ {f.detail}</div>)}
            </div>
          )}
        </Card>
        <Card title="Genre taxonomy" className="xl:col-span-2" action={
          <select value={family} onChange={(e) => setFamily(e.target.value)}><option value="">all families</option>{["structural", "cultural", "nature", "narrative"].map((f) => <option key={f}>{f}</option>)}</select>}>
          <div className="grid grid-cols-1 max-h-[460px] gap-2 overflow-auto pr-1 md:grid-cols-2">
            {list.map((g: any) => (
              <button key={g.id} onClick={() => setPicked((p) => p.includes(g.id) || p.length >= 4 ? p : [...p, g.id])}
                className="rounded-md border border-line bg-bg/50 p-2.5 text-left hover:border-violet-dim">
                <div className="flex items-center justify-between gap-2"><span className="text-[13px] font-medium">{g.name}</span><Swatches colors={g.palette} size={12} /></div>
                <div className="mt-0.5 text-[11.5px] text-ink-3">{g.description}</div>
                <div className="mt-1 font-mono text-[10px] uppercase text-ink-3">{g.family}{g.pillar && " · pillar D"} · video {Math.round(g.video_fit * 100)} · used in {g.used_in_hybrids} hybrids{g.sensitivity.length ? ` · review: ${g.sensitivity.join(", ")}` : ""}</div>
              </button>
            ))}
          </div>
        </Card>
      </div>

      <div className="mt-4 grid grid-cols-1 gap-4 xl:grid-cols-2">
        <Card title="Originality scores · recent concepts" action={<Link href="/flare/brands" className="text-[12px] text-violet hover:underline">Brand Laboratory →</Link>} pad={false}>
          {recent.length ? (
            <Table head={["Concept", "Genres", "Originality", "Status", "Author"]}>
              {recent.map((c) => (
                <tr key={c.id}><td className="font-medium">{c.name}</td><td className="text-[12px] text-ink-3">{label(c.primary_genre)} × {label(c.secondary_genre)}</td>
                  <td className="num">{c.originality?.score?.toFixed(0)}</td><td className="text-ink-2">{c.status}</td><td className="text-ink-3">{c.author_persona}</td></tr>
              ))}
            </Table>
          ) : <div className="p-4"><Empty title="No concepts yet">Run a creative competition in the Brand Laboratory.</Empty></div>}
        </Card>
        <Card title="Style DNA · genre evolution (evidence only)">
          {Object.keys(dna.data?.evidence ?? {}).length ? (
            <Table head={["Feature", "Obs.", "Spend", "Profit", "Adjustment"]}>
              {Object.entries(dna.data.evidence).map(([k, v]: any) => {
                const [kind, id] = k.split(":");
                return <tr key={k}><td>{kind}: {label(id)}</td><td className="num">{v.observations}</td><td className="num">{v.spend}</td><td className="num">{v.profit}</td>
                  <td className="num">{(dna.data[kind]?.[id] ?? 0) > 0 ? "+" : ""}{dna.data[kind]?.[id]}</td></tr>;
              })}
            </Table>
          ) : <Empty title="Insufficient evidence">Style DNA learns only from recorded campaign performance. {evo.data?.how_to_feed}</Empty>}
          {evo.data?.performance_trends?.length > 0 && <div className="mt-3 text-[12.5px] text-ink-2">Trends: {evo.data.performance_trends.map((t: any) => `${label(t.genre)} ${t.direction}`).join(" · ")}</div>}
        </Card>
      </div>
    </>
  );
}
