"use client";
import Link from "next/link";
import { useState } from "react";
import { ConceptCard, ProductPicker, SvgAsset, Swatches } from "@/components/flare";
import { Button, Card, Empty, ErrorBanner, PageHeader, Table } from "@/components/ui";
import { api } from "@/lib/api";
import { label, useRun } from "@/lib/flare";
import { useApi, useRefreshOn } from "@/lib/hooks";

export default function BrandLab() {
  const [pid, setPid] = useState<number | null>(null);
  const concepts = useApi<any[]>(`/api/flare/concepts${pid ? `?product_id=${pid}` : ""}`, [pid]);
  const [open, setOpen] = useState<number | null>(null);
  const [cmp, setCmp] = useState<number[]>([]);
  const [compare, setCompare] = useState<any[] | null>(null);
  const { run, busy, error, setError } = useRun();
  useRefreshOn(["task"], concepts.reload);
  const go = async (type: string, payload: any) => { const t = await run(type, payload); concepts.reload(); return t; };
  const doCompare = async () => { try { setCompare(await api("/api/flare/concepts/compare", { method: "POST", json: { ids: cmp } })); } catch (e) { setError((e as Error).message); } };

  return (
    <>
      <PageHeader kicker="Rocky Flare · brand laboratory" title="Brand concepts, competitions & reviews">
        <ProductPicker value={pid} onChange={setPid} />
      </PageHeader>
      <ErrorBanner error={error || concepts.error} />
      <Card title="Run creative workflows" className="mb-4">
        <div className="flex flex-wrap gap-2">
          <Button variant="primary" disabled={!pid} busy={busy === "flare.competition"} onClick={() => go("flare.competition", { product_id: pid })}>Creative competition (5 creatives)</Button>
          <Button disabled={!pid} busy={busy === "flare.panel"} onClick={() => go("flare.panel", { product_id: pid })}>Review panel</Button>
          <Button disabled={!pid} busy={busy === "flare.discussion"} onClick={() => go("flare.discussion", { product_id: pid })}>Agent discussion</Button>
          <Button disabled={cmp.length < 2} onClick={doCompare}>Compare selected ({cmp.length})</Button>
          <Link href="/flare/collab" className="self-center text-[12px] text-violet hover:underline">Collaboration log →</Link>
        </div>
        <p className="mt-2 text-[12px] text-ink-3">Competitors develop concepts independently; judges score every concept through their own lens. All concepts are kept; shortlisting is not approval.</p>
      </Card>

      {compare && (
        <Card title="Side-by-side comparison" className="mb-4" action={<button className="text-[12px] text-ink-3" onClick={() => setCompare(null)}>close</button>} pad={false}>
          <Table head={["", ...compare.map((c) => c.name)]}>
            {([["Genres", (c: any) => c.genres.join(" × ")], ["Palette", (c: any) => <Swatches colors={c.palette} size={14} />], ["Positioning", (c: any) => c.positioning],
              ["Originality", (c: any) => c.originality?.toFixed(0)], ["Panel mean", (c: any) => c.panel_mean ?? "—"],
              ["Audience relevance", (c: any) => c.evaluation?.audience_relevance], ["Differentiation", (c: any) => c.evaluation?.competitive_differentiation],
              ["Visual recognition", (c: any) => c.evaluation?.visual_recognition], ["Marketing potential", (c: any) => c.evaluation?.marketing_potential],
              ["Production cost (↑ cheaper)", (c: any) => c.evaluation?.production_cost], ["Flags", (c: any) => c.flags.join(", ") || "—"], ["Author", (c: any) => c.author]] as const)
              .map(([k, f]) => <tr key={k}><td className="text-ink-3">{k}</td>{compare.map((c) => <td key={c.id} className="num text-[12.5px]">{f(c)}</td>)}</tr>)}
          </Table>
        </Card>
      )}

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1fr)_520px]">
        <Card title={`${concepts.data?.length ?? 0} concepts (latest versions)`}>
          {concepts.data?.length ? (
            <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
              {concepts.data.map((c) => <ConceptCard key={c.id} c={c} selected={cmp.includes(c.id)} onOpen={() => setOpen(c.id)}
                onSelect={() => setCmp((x) => x.includes(c.id) ? x.filter((i) => i !== c.id) : [...x, c.id].slice(-4))} />)}
            </div>
          ) : <Empty title="No concepts yet">Pick a product and run a creative competition.</Empty>}
        </Card>
        {open ? <ConceptDetail id={open} onChange={concepts.reload} run={go} busy={busy} onError={setError} /> : <Card><Empty title="Open a concept" /></Card>}
      </div>
    </>
  );
}

function ConceptDetail({ id, onChange, run, busy, onError }: { id: number; onChange: () => void; run: (t: string, p: any) => Promise<any>; busy: string | null; onError: (e: string) => void }) {
  const c = useApi<any>(`/api/flare/concepts/${id}`, [id]);
  useRefreshOn(["task"], c.reload);
  const d = c.data;
  if (!d) return null;
  const status = async (s: string) => { try { await api(`/api/flare/concepts/${id}/status`, { method: "POST", json: { status: s } }); c.reload(); onChange(); } catch (e) { onError((e as Error).message); } };
  const brand = async () => { try { await api("/api/flare/brands", { method: "POST", json: { concept_id: id } }); c.reload(); } catch (e) { onError((e as Error).message); } };
  const visuals = d.assets.filter((a: any) => a.mime === "image/svg+xml");
  const briefs = d.assets.filter((a: any) => a.mime === "text/plain");
  const flags = d.originality?.flags ?? [];
  return (
    <Card title={`${d.name} · v${d.version}`} action={<span className="text-[12px] text-ink-3">{d.status}</span>}>
      <p className="text-[13px] italic text-ink-2">{d.tagline}</p>
      <p className="mt-2 text-[12.5px] text-ink-2">{d.story}</p>
      <dl className="mt-3 grid grid-cols-[110px_minmax(0,1fr)] gap-y-1 text-[12px]">
        <dt className="text-ink-3">Audience</dt><dd>{d.audience}</dd><dt className="text-ink-3">USP</dt><dd>{d.usp}</dd>
        <dt className="text-ink-3">Genres</dt><dd>{label(d.primary_genre)} × {label(d.secondary_genre)}</dd>
        <dt className="text-ink-3">Typography</dt><dd>{d.direction?.typography?.display} / {d.direction?.typography?.text}</dd>
        <dt className="text-ink-3">Materials</dt><dd>{(d.direction?.materials_textures ?? []).join(", ")}</dd>
        <dt className="text-ink-3">Packaging</dt><dd>{d.direction?.packaging_style}</dd><dt className="text-ink-3">Photography</dt><dd>{d.direction?.photography_style}</dd>
        <dt className="text-ink-3">Website</dt><dd>{d.direction?.website_language}</dd><dt className="text-ink-3">Social</dt><dd>{d.direction?.social_identity}</dd>
        <dt className="text-ink-3">Advertising</dt><dd>{d.direction?.advertising_direction}</dd>
      </dl>
      <div className="mt-3 rounded-md border border-line bg-bg/50 p-2.5">
        <div className="text-[12px] text-ink-2">Originality <b className="num">{d.originality?.score}</b> — {Object.entries(d.originality?.components ?? {}).map(([k, v]) => `${label(k)} ${v}`).join(" · ")}</div>
        {flags.map((f: any, i: number) => <div key={i} className={`text-[11.5px] ${f.severity === "block" ? "text-[#f08a8a]" : "text-warning"}`}>{f.severity}: {f.detail}</div>)}
        <div className="mt-1 text-[11px] text-ink-3">{d.originality?.trademark?.required}</div>
      </div>
      <div className="mt-3 flex flex-wrap gap-2">
        <Button busy={busy === "flare.assets"} onClick={() => run("flare.assets", { concept_id: id })}>Generate assets</Button>
        <Button busy={busy === "flare.revise"} onClick={() => run("flare.revise", { concept_id: id })}>Revise → new version</Button>
        <Button busy={busy === "flare.campaign_matrix"} onClick={() => run("flare.campaign_matrix", { product_id: d.product_id, concept_id: id })}>Campaign matrix</Button>
        <Button onClick={() => status("shortlisted")}>Shortlist</Button>
        <Button variant="primary" disabled={d.originality?.requires_revision} onClick={() => status("approved")}>Approve (admin)</Button>
        <Button variant="danger" onClick={() => status("rejected")}>Reject</Button>
        {d.status === "approved" && !d.brand_id && <Button variant="primary" onClick={brand}>Create brand</Button>}
      </div>
      {visuals.length > 0 && <div className="mt-4 grid grid-cols-2 gap-2">{visuals.map((a: any) => <figure key={a.id}><SvgAsset svg={a.content} alt={a.title} className="w-full" /><figcaption className="mt-0.5 text-[11px] text-ink-3">{a.title}</figcaption></figure>)}</div>}
      {briefs.length > 0 && <details className="mt-3"><summary className="cursor-pointer text-[12px] text-ink-3">{briefs.length} briefs</summary>{briefs.map((a: any) => <pre key={a.id} className="mt-2 whitespace-pre-wrap rounded bg-bg p-2 text-[11.5px] text-ink-2">{a.content}</pre>)}</details>}
      <div className="mt-4 text-[12px]"><b className="text-ink-2">Versions:</b> {d.versions.map((v: any) => `v${v.version} ${v.name} (${v.originality?.toFixed?.(0)})`).join(" → ")}</div>
      {d.reviews.length > 0 && <div className="mt-3 space-y-1.5">{d.reviews.map((r: any) => <div key={r.id} className="text-[12px] text-ink-2"><b>{r.persona_id}</b> · {r.stance} · {r.scores.weighted_score}: <span className="text-ink-3">{r.message}</span></div>)}</div>}
      {d.reuse_suggestions.length > 0 && <div className="mt-3 text-[12px] text-ink-3">Reusable from other brands: {d.reuse_suggestions.map((r: any) => `${r.type} (${r.shared_genres.join(", ")})`).join(" · ")}</div>}
    </Card>
  );
}
