"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { ProductPicker, Swatches } from "@/components/flare";
import { Button, Card, DemoBadge, Empty, ErrorBanner, Field, PageHeader, ScoreBar, StatusBadge, Table } from "@/components/ui";
import { api, pct } from "@/lib/api";
import { label, useRun } from "@/lib/flare";
import { useApi } from "@/lib/hooks";

const TABS = [
  ["tactical", "Tactical Intelligence"], ["survival", "Survival Radar"], ["nordic", "Nordic Preparedness"], ["escooter", "E-Scooter Laboratory"],
  ["ebike", "E-Bike Laboratory"], ["edc", "EDC Design Studio"], ["bushcraft", "Bushcraft & Outdoor"], ["archive", "Ancient Design Archive"],
  ["fusion", "Genre Fusion Lab"], ["modular", "Modular Product Systems"], ["suppliers", "Supplier Intelligence"], ["brands", "Brand Factory"],
  ["innovation", "Product Innovation"], ["council", "Creative Council"],
] as const;
const PRODUCT_TABS = new Set(["tactical", "survival", "nordic", "escooter", "ebike", "edc", "bushcraft"]);
const SEGMENT_FOR: Record<string, string[]> = {
  tactical: ["minimalist_edc", "tradespeople", "urban_commuters"], survival: ["preparedness", "off_grid", "outdoor_enthusiasts"],
  nordic: ["nordic_winter_commuters", "preparedness", "ebike_commuters"], escooter: ["escooter_owners", "urban_commuters"],
  ebike: ["ebike_commuters", "cyclists", "nordic_winter_commuters"], edc: ["minimalist_edc", "travellers", "diy"],
  bushcraft: ["bushcraft", "hikers", "campers", "outdoor_photographers"],
};
const FIELD_COMPETITORS = ["tactical_brand_strategist", "ancient_symbolism_ad", "edc_designer", "nordic_preparedness", "tactical_design_director"];

export default function FieldOps() {
  const [tab, setTab] = useState<string>("tactical");
  useEffect(() => { const h = window.location.hash.slice(1); if (h) setTab(h); }, []);
  const ov = useApi<any>("/api/field/overview");
  const pick = (t: string) => { setTab(t); history.replaceState(null, "", `#${t}`); };
  return (
    <div className="field-bg -mx-4 -my-6 min-h-full px-4 py-6 md:-mx-8 md:px-8">
      <PageHeader kicker="Rocky Flare // Survival, tactical & mobility division" title="Field Operations">
        <span className="font-mono text-[11px] uppercase tracking-[0.3em] text-gold">Prepare · Adapt · Explore · Create</span>
      </PageHeader>
      <div className="parchment-rule mb-4" />
      {ov.data && (
        <div className="mb-4 grid grid-cols-2 gap-3 md:grid-cols-4">
          {Object.entries(ov.data.pillars).map(([k, v]: any) => (
            <div key={k} className="rounded-lg border border-bronze/40 bg-char/80 px-4 py-3">
              <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-gold">Pillar {k[0]}</div>
              <div className="text-[14px] font-medium text-parchment">{v.label}</div>
              <div className="num text-[12px] text-ink-3">{v.products} products in catalogue</div>
            </div>
          ))}
        </div>
      )}
      <div className="mb-4 flex flex-wrap gap-1">
        {TABS.map(([id, name]) => (
          <button key={id} onClick={() => pick(id)} className={`rounded-md border px-2.5 py-1 text-[12px] ${tab === id ? "border-gold bg-gold/10 text-parchment" : "border-line text-ink-3 hover:border-bronze hover:text-ink-2"}`}>
            {name}{PRODUCT_TABS.has(id) && ov.data ? <span className="num ml-1 text-ink-3">{ov.data.subsections[id]}</span> : null}
          </button>
        ))}
      </div>
      {PRODUCT_TABS.has(tab) ? <ProductBoard sub={tab} /> : tab === "archive" ? <Archive /> : tab === "fusion" ? <Fusion /> : tab === "modular" ? <Modular />
        : tab === "suppliers" ? <Suppliers /> : tab === "brands" ? <BrandFactory /> : tab === "innovation" ? <Innovation /> : <Council />}
    </div>
  );
}

function ProductBoard({ sub }: { sub: string }) {
  const prods = useApi<any[]>(`/api/field/products?sub=${sub}`, [sub]);
  const segs = useApi<any[]>("/api/field/segments");
  const mine = (segs.data ?? []).filter((s) => SEGMENT_FOR[sub]?.includes(s.id));
  return (
    <div className="grid gap-4 xl:grid-cols-[1fr_420px]">
      <Card title="Product board" pad={false}>
        {prods.data?.length ? (
          <Table head={["Product", "Pillars", "Score · coverage", "Net margin", "Compliance", "Mobility class", "Verified fits"]}>
            {prods.data.map((p) => (
              <tr key={p.id}><td className="font-medium"><Link className="hover:text-gold" href={`/lab/${p.id}`}>{p.name}</Link><DemoBadge show={p.is_demo} /></td>
                <td className="text-[11px] text-ink-3">{p.pillars.map((x: string) => x[0]).join(" ")}</td>
                <td><ScoreBar score={p.opportunity_score} confidence={p.score_confidence} /></td><td className="num">{pct(p.net_margin)}</td>
                <td><StatusBadge status={p.compliance_status} /></td><td className="text-[12px] text-ink-2">{p.mobility_class ? label(p.mobility_class) : "—"}</td>
                <td className="num">{p.compatibility_verified}</td></tr>
            ))}
          </Table>
        ) : <div className="p-4"><Empty title="Nothing in this section yet">Import or research products for this pillar (or load the demo dataset).</Empty></div>}
      </Card>
      <Card title="Customer segments (hypotheses to validate)">
        {mine.map((s) => (
          <div key={s.id} className="mb-3 border-b border-line/60 pb-3 last:border-0">
            <div className="text-[13px] font-medium text-parchment">{s.label} <span className="text-[11px] font-normal text-ink-3">price sensitivity: {s.price_sensitivity}</span></div>
            <div className="text-[12px] text-ink-2">Problems: {s.problems.join("; ")}</div>
            <div className="text-[12px] text-ink-3">Unmet: {s.unmet.join("; ")} · Subscriptions: {s.subscriptions}</div>
            <div className="text-[11.5px] text-ink-3">Genres: {s.genres.map(label).join(", ")}</div>
          </div>
        ))}
      </Card>
    </div>
  );
}

function Archive() {
  const a = useApi<any>("/api/field/archive");
  if (!a.data) return null;
  return (
    <>
      <Card title="Rules for pillar D" className="mb-4"><ul className="grid gap-1 text-[12.5px] text-parchment md:grid-cols-2">{a.data.rules.map((r: string) => <li key={r}>✦ {r}</li>)}</ul></Card>
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {a.data.genres.map((g: any) => (
          <div key={g.id} className="rounded-lg border border-bronze/40 bg-char/80 p-3">
            <div className="flex items-center justify-between"><span className="text-[14px] font-medium text-parchment">{g.name}</span><Swatches colors={g.palette} size={12} /></div>
            <p className="mt-1 text-[12px] text-ink-2">{g.description}</p>
            <p className="mt-1 text-[11.5px] text-ink-3">{g.graphic_language}</p>
            <p className="mt-1 font-mono text-[10.5px] text-gold">{g.vocab.join(" · ")}</p>
            {g.sensitivity.length > 0 && <p className="mt-1 text-[11px] text-warning">review: {g.sensitivity.join(", ")}</p>}
          </div>
        ))}
      </div>
      <Card title="Reference hybrids from the brief (names are starting points only)" className="mt-4" pad={false}>
        <Table head={["Hybrid", "Components", "Palette", "Trademark pre-screen"]}>
          {a.data.presets.map((h: any) => {
            const tm = a.data.preset_trademark_checks[h.name];
            return <tr key={h.id}><td className="font-medium text-parchment">{h.name}</td><td className="text-[12px] text-ink-3">{h.components.map(label).join(" + ")}</td>
              <td><Swatches colors={h.palette} size={12} /></td>
              <td className="text-[12px]">{tm.status === "known_conflict" ? <span className="text-[#f08a8a]">conflict: {tm.hits.map((x: any) => x.note).join("; ")}</span> : <span className="text-ink-3">{tm.hits.length ? tm.hits.map((x: any) => x.note).join("; ") : "no known mark — official search still required"}</span>}</td></tr>;
          })}
        </Table>
      </Card>
    </>
  );
}

function Fusion() {
  const g = useApi<any>("/api/flare/genres");
  const [picked, setPicked] = useState<string[]>([]);
  const [h, setH] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);
  const fuse = async () => { try { setH(await api("/api/flare/genres/fuse", { method: "POST", json: { components: picked } })); setErr(null); } catch (e) { setErr((e as Error).message); } };
  const order = ["tactical_utility", "industrial", "nordic_survival", "urban_commuter", "expedition_nomad", "outdoor_adventure", "cyberpunk", "streetwear", "scandi_minimal", "luxury", "future_tech"];
  const pillarD = (g.data?.genres ?? []).filter((x: any) => x.pillar === "D");
  const field = (g.data?.genres ?? []).filter((x: any) => order.includes(x.id));
  return (
    <div className="grid gap-4 xl:grid-cols-2">
      <Card title="Combine the four pillars">
        <ErrorBanner error={err} />
        <div className="mb-2 font-mono text-[10.5px] uppercase text-gold">Function & mobility</div>
        <div className="mb-3 flex flex-wrap gap-1.5">{field.map((x: any) => <button key={x.id} onClick={() => setPicked((p) => p.includes(x.id) ? p.filter((y) => y !== x.id) : [...p, x.id].slice(-4))} className={`rounded border px-2 py-0.5 text-[12px] ${picked.includes(x.id) ? "border-gold text-parchment" : "border-line-strong text-ink-3"}`}>{x.name}</button>)}</div>
        <div className="mb-2 font-mono text-[10.5px] uppercase text-gold">Ancient, spiritual & esoteric</div>
        <div className="mb-3 flex flex-wrap gap-1.5">{pillarD.map((x: any) => <button key={x.id} onClick={() => setPicked((p) => p.includes(x.id) ? p.filter((y) => y !== x.id) : [...p, x.id].slice(-4))} className={`rounded border px-2 py-0.5 text-[12px] ${picked.includes(x.id) ? "border-gold text-parchment" : "border-line-strong text-ink-3"}`}>{x.name}</button>)}</div>
        <div className="flex items-center gap-2"><span className="text-[12px] text-ink-3">{picked.map(label).join(" + ") || "pick 2–4"}</span><Button variant="primary" disabled={picked.length < 2} onClick={fuse}>Generate genre</Button></div>
      </Card>
      <Card title="Generated genre">
        {h ? (
          <dl className="grid grid-cols-[130px_1fr] gap-y-1.5 text-[12.5px]">
            <dt className="text-ink-3">Name</dt><dd className="text-[15px] font-semibold text-parchment">{h.name} {h.novel && <span className="text-[11px] text-gold">· new hybrid</span>}</dd>
            <dt className="text-ink-3">Concept</dt><dd>{h.concept}</dd><dt className="text-ink-3">Philosophy</dt><dd>{h.philosophy}</dd>
            <dt className="text-ink-3">Audience</dt><dd>{h.target_audience}</dd><dt className="text-ink-3">Palette</dt><dd><Swatches colors={h.palette} /></dd>
            <dt className="text-ink-3">Typography</dt><dd>{h.typography.display} / {h.typography.text}</dd><dt className="text-ink-3">Materials</dt><dd>{h.materials.join(", ")}</dd>
            <dt className="text-ink-3">Surfaces</dt><dd>{h.surface_treatments.join(", ")}</dd><dt className="text-ink-3">Graphic language</dt><dd>{h.graphic_language}</dd>
            <dt className="text-ink-3">Applications</dt><dd>{h.product_applications.join(", ")}</dd><dt className="text-ink-3">Packaging</dt><dd>{h.packaging_direction}</dd>
            <dt className="text-ink-3">Photography</dt><dd>{h.photography_direction}</dd><dt className="text-ink-3">Marketing identity</dt><dd>{h.marketing_identity}</dd>
            <dt className="text-ink-3">Reviews</dt><dd className="text-warning">{[...h.originality_flags.map((f: any) => f.detail), ...h.trademark.hits.map((x: any) => x.note)].join(" · ") || "—"}</dd>
          </dl>
        ) : <Empty title="Fuse a structural genre with a narrative one" />}
      </Card>
    </div>
  );
}

function Modular() {
  const e = useApi<any>("/api/field/ecosystems");
  return (
    <div className="grid gap-4 xl:grid-cols-2">
      {(e.data?.ecosystems ?? []).map((x: any) => (
        <Card key={x.template} title={`${x.label} · ${Math.round(x.coverage * 100)}% covered`}>
          <div className="grid gap-2 md:grid-cols-2">{x.modules.map((m: any) => (
            <div key={m.id} className={`rounded-md border p-2.5 ${m.products.length ? "border-olive bg-olive/10" : "border-dashed border-line-strong"}`}>
              <div className="text-[13px] text-parchment">{m.label}</div>
              <div className="text-[11.5px] text-ink-3">{m.products.length ? m.products.map((p: any) => p.name).join(", ") : m.status}</div>
            </div>))}</div>
          <p className="mt-2 text-[11.5px] text-ink-3">{x.note}</p>
        </Card>
      ))}
      <Card title="Mounting standards (compatibility opportunities)" pad={false}>
        <Table head={["Standard", "Typical use", "Verify"]}>{(e.data?.mounting_standards ?? []).map((m: any) => <tr key={m.id}><td className="text-parchment">{m.name}</td><td className="text-ink-2">{m.applies}</td><td className="text-[12px] text-ink-3">{m.verify}</td></tr>)}</Table>
      </Card>
    </div>
  );
}

function Suppliers() {
  const [pid, setPid] = useState<number | null>(null);
  const s = useApi<any[]>(pid ? `/api/field/suppliers?product_id=${pid}` : null, [pid]);
  return (
    <Card title="Nordic-first sourcing assessment" action={<ProductPicker value={pid} onChange={setPid} />} pad={false}>
      {s.data?.length ? (
        <Table head={["Supplier", "Region", "Score", "Spare parts", "Warranty", "Documents missing", ""]}>
          {s.data.map((r) => (
            <tr key={r.supplier_id} className="align-top"><td className="font-medium">{r.name}<DemoBadge show={r.is_demo} /></td><td>{r.region_label} <span className="text-ink-3">({r.country})</span></td>
              <td className="num">{r.score}</td><td>{r.spare_parts ? "yes" : "no"}</td><td className="num">{r.warranty_months ?? "—"}</td>
              <td className="max-w-md text-[12px] text-warning">{r.documents_missing.join("; ") || <span className="text-good">none required/missing</span>}</td>
              <td>{r.safety_critical && <StatusBadge status="restricted" />}</td></tr>
          ))}
        </Table>
      ) : <div className="p-4"><Empty title={pid ? "No suppliers recorded" : "Pick a product"}>Ranking: Sweden → Nordics → EU → rest; safety-critical items require documents before any order.</Empty></div>}
    </Card>
  );
}

function BrandFactory() {
  const [pid, setPid] = useState<number | null>(null);
  const { run, busy, error } = useRun();
  const [sid, setSid] = useState<number | null>(null);
  const s = useApi<any>(sid ? `/api/flare/sessions/${sid}` : null, [sid]);
  return (
    <>
      <ErrorBanner error={error} />
      <Card title="Tactical brand factory — five field creatives compete independently" className="mb-4">
        <div className="flex flex-wrap items-center gap-2"><ProductPicker value={pid} onChange={setPid} />
          <Button variant="primary" disabled={!pid} busy={busy === "flare.competition"} onClick={async () => { const t = await run("flare.competition", { product_id: pid, competitors: FIELD_COMPETITORS, topic: "Field brand factory" }); if (t?.result) setSid(t.result.session_id); }}>Run brand factory</Button></div>
        <p className="mt-2 text-[12px] text-ink-3">Competitors: {FIELD_COMPETITORS.map(label).join(", ")}. Names are checked against known marks; an official EUIPO/PRV search is always required.</p>
      </Card>
      {s.data && (
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {s.data.concepts.map((c: any) => {
            const r = s.data.decision?.ranking?.find((x: any) => x.concept_id === c.id);
            return (
              <div key={c.id} className="rounded-lg border border-bronze/40 bg-char/80 p-3">
                <div className="flex justify-between"><b className="text-parchment">{c.name}</b><span className="num text-gold">{r?.mean ?? "—"}</span></div>
                <div className="text-[12px] italic text-ink-2">{c.tagline}</div>
                <div className="my-1.5"><Swatches colors={c.direction?.color_palette ?? []} size={14} /></div>
                <div className="text-[11.5px] text-ink-3">{label(c.primary_genre)} × {label(c.secondary_genre)} · by {c.author_persona} · originality {c.originality?.score}</div>
                {r?.consensus === "split" && <div className="text-[11px] text-warning">split verdict ±{r.stdev}</div>}
              </div>
            );
          })}
        </div>
      )}
    </>
  );
}

function Innovation() {
  const [pid, setPid] = useState<number | null>(null);
  const inn = useApi<any>(pid ? `/api/field/innovation/${pid}` : null, [pid]);
  const compat = useApi<any[]>(pid ? `/api/field/compatibility?product_id=${pid}` : null, [pid]);
  const [f, setF] = useState({ target: "", target_kind: "vehicle_model", status: "unverified", evidence: "" });
  const [err, setErr] = useState<string | null>(null);
  const add = async () => { try { await api("/api/field/compatibility", { method: "POST", json: { ...f, product_id: pid } }); compat.reload(); setErr(null); } catch (e) { setErr((e as Error).message); } };
  return (
    <div className="grid gap-4 xl:grid-cols-2">
      <Card title="Survival product innovation lab" action={<ProductPicker value={pid} onChange={setPid} />} pad={false}>
        {inn.data ? (
          <Table head={["Question", "Proposed design", "Functional", "Risk", "Verify first"]}>
            {inn.data.innovation.map((i: any) => <tr key={i.key}><td className="text-parchment">{i.question}</td><td className="text-[12px]">{i.proposal}<div className="text-[10.5px] text-ink-3">{label(i.status)}</div></td>
              <td className="num">{i.functional_value}</td><td className="num">{i.regulatory_risk}</td><td className="text-[11.5px] text-ink-3">{i.verification}</td></tr>)}
          </Table>
        ) : <div className="p-4"><Empty title="Pick a product" /></div>}
      </Card>
      <Card title="Compatibility matrix (never assumed)">
        <ErrorBanner error={err} />
        {pid ? (
          <>
            <Table head={["Target", "Kind", "Status", "Evidence", "By"]}>
              {(compat.data ?? []).map((c) => <tr key={c.id}><td>{c.target}</td><td className="text-ink-3">{label(c.target_kind)}</td><td><StatusBadge status={c.status === "verified" ? "approved" : c.status === "incompatible" ? "blocked" : "pending"} /> <span className="text-[11px] text-ink-3">{label(c.status)}</span></td><td className="max-w-xs text-[12px] text-ink-3">{c.evidence}</td><td className="text-[12px] text-ink-3">{c.verified_by}</td></tr>)}
            </Table>
            <div className="mt-3 grid grid-cols-2 gap-2">
              <Field label="Model or mount standard"><input value={f.target} onChange={(e) => setF({ ...f, target: e.target.value })} placeholder="e.g. Handlebar Ø22.2 mm" /></Field>
              <Field label="Kind"><select value={f.target_kind} onChange={(e) => setF({ ...f, target_kind: e.target.value })}><option value="vehicle_model">vehicle model</option><option value="mount_standard">mount standard</option></select></Field>
              <Field label="Status"><select value={f.status} onChange={(e) => setF({ ...f, status: e.target.value })}>{["unverified", "supplier_claimed", "verified", "incompatible"].map((s) => <option key={s}>{s}</option>)}</select></Field>
              <Field label="Evidence (required for verified)"><input value={f.evidence} onChange={(e) => setF({ ...f, evidence: e.target.value })} placeholder="test, date, model/year" /></Field>
            </div>
            <div className="mt-2"><Button disabled={f.target.length < 2} onClick={add}>Record</Button></div>
          </>
        ) : <Empty title="Pick a product" />}
      </Card>
    </div>
  );
}

function Council() {
  const [pid, setPid] = useState<number | null>(null);
  const { run, busy, error } = useRun();
  const sessions = useApi<any[]>("/api/flare/sessions?kind=council");
  const [sid, setSid] = useState<number | null>(null);
  const s = useApi<any>(sid ? `/api/flare/sessions/${sid}` : null, [sid]);
  const c = s.data?.decision?.council;
  return (
    <>
      <ErrorBanner error={error} />
      <Card title="Creative council — 8 independent seats, no forced consensus" className="mb-4">
        <div className="flex flex-wrap items-center gap-2"><ProductPicker value={pid} onChange={setPid} />
          <Button variant="primary" disabled={!pid} busy={busy === "flare.council"} onClick={async () => { const t = await run("flare.council", { product_id: pid }); if (t?.result) { setSid(t.result.session_id); sessions.reload(); } }}>Convene council</Button>
          <select value={sid ?? ""} onChange={(e) => setSid(Number(e.target.value))}><option value="">previous councils…</option>{(sessions.data ?? []).map((x) => <option key={x.id} value={x.id}>#{x.id} {x.topic}</option>)}</select></div>
        <p className="mt-2 text-[12px] text-ink-3">Seats: Rocky Flare Creative Director · Tactical Product Designer · Survival Specialist · E-Mobility Engineer · Ancient Symbolism Art Director · Commercial Strategist · CFO · Devil's Advocate</p>
      </Card>
      {c && (
        <div className="grid gap-4 xl:grid-cols-3">
          <Card title="Best functional design">{c.best_functional_design ? <><div className="text-parchment">{c.best_functional_design.question}</div><div className="text-[12px] text-ink-2">{c.best_functional_design.proposal}</div><div className="text-[11.5px] text-ink-3">verify: {c.best_functional_design.verification}</div></> : "—"}</Card>
          <Card title="Best creative direction">{c.best_creative_direction ? <><div className="text-parchment">{c.best_creative_direction.name}</div><div className="num text-[12px] text-ink-3">mean {c.best_creative_direction.mean} ±{c.best_creative_direction.stdev} · {c.best_creative_direction.consensus}</div></> : "—"}</Card>
          <Card title="Best brand opportunity">{c.best_brand_opportunity ? <><div className="text-parchment">{c.best_brand_opportunity.name}</div><div className="num text-[12px] text-ink-3">mean {c.best_brand_opportunity.mean}</div></> : "No concept passed the originality gate"}</Card>
          <Card title="Best monetization strategy"><div className="text-[12.5px]">{c.best_monetization_strategy.business_models.map((m: any) => label(m.model)).join(", ") || "—"}</div><div className="text-[12px] text-ink-3">Recurring: {c.best_monetization_strategy.recurring.title} — {c.best_monetization_strategy.recurring.reasoning.join("; ")}</div></Card>
          <Card title="Main technical risks"><ul className="space-y-1 text-[12px] text-ink-2">{c.main_technical_risks.map((r: string, i: number) => <li key={i}>• {r}</li>)}</ul></Card>
          <Card title="Main regulatory risks"><ul className="space-y-1 text-[12px] text-warning">{c.main_regulatory_risks.map((r: string, i: number) => <li key={i}>• {r}</li>)}</ul></Card>
          <Card title="Recommended next experiment" className="xl:col-span-3"><div className="text-[13px] text-parchment">{c.recommended_next_experiment.type}</div>
            <div className="text-[12.5px] text-ink-2">Budget: {c.recommended_next_experiment.budget_sek ?? "—"} SEK · Success: {c.recommended_next_experiment.success_metric}</div>
            <div className="text-[12px] text-ink-3">{c.recommended_next_experiment.note}</div></Card>
          <Card title="Seat verdicts" className="xl:col-span-3" pad={false}>
            <Table head={["Seat", "Concept", "Score", "Stance", "Message"]}>
              {s.data.turns.map((t: any) => <tr key={t.id} className="align-top"><td className="text-parchment">{t.persona_name}</td><td className="num">{t.scores?.concept_id}</td><td className="num">{t.scores?.weighted_score}</td><td>{t.stance}</td><td className="text-[12px] text-ink-3">{t.message}</td></tr>)}
            </Table>
          </Card>
        </div>
      )}
    </>
  );
}
