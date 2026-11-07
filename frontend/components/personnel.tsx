"use client";
/** Astral personnel UI: species sigils, evidence-class labels, agent cards and the G-SUS agent proposal card.
 *  Sigils are drawn here as React SVG (never HTML from the API). Each family has its own silhouette so a fairy does
 *  not look like a small demon and a Sasquatch does not look like a goblin; colour varies per species but is never the
 *  only signal — every card names the species in text. */
import Link from "next/link";
import { BookOpen, Feather, Info, Lightbulb, ScrollText, ShieldAlert, Sparkles, User } from "lucide-react";
import { useState, type ReactNode } from "react";
import { Button, ErrorBanner, StatusBadge } from "@/components/ui";
import { api } from "@/lib/api";

// ------------------------------------------------------------------------------------------------ sigils
const PALETTE: Record<string, string[]> = {
  fae: ["violet", "cyan", "series-3"], elves: ["series-3", "cyan", "parchment"], leprechauns: ["good", "gold"],
  spirits: ["violet", "serious", "cyan"], elementals: ["serious", "series-1", "cyan", "bronze"], nordic: ["parchment", "bronze", "cyan"],
  european: ["gold", "bronze", "serious"], cryptids: ["olive", "bronze"], asian: ["serious", "gold", "violet"], canon: ["violet", "gold"],
  custom: ["cyan", "violet"],
};
const hash = (s: string) => [...s].reduce((h, c) => (h * 31 + c.charCodeAt(0)) >>> 0, 7);

type G = () => ReactNode;
const P = { fill: "none", stroke: "currentColor", strokeWidth: 2.4, strokeLinecap: "round" as const, strokeLinejoin: "round" as const };
const wings: G = () => <g {...P}><ellipse cx="22" cy="28" rx="10" ry="14" transform="rotate(-25 22 28)" /><ellipse cx="42" cy="28" rx="10" ry="14" transform="rotate(25 42 28)" /><path d="M32 22v22" /><circle cx="32" cy="18" r="3" /></g>;
const leaf: G = () => <g {...P}><path d="M18 46c0-18 12-28 28-30-2 16-12 28-28 30z" /><path d="M18 46l20-22" /><path d="M46 44l2 4 4 1-4 2-1 4-2-4-4-1 4-2z" /></g>;
const hat: G = () => <g {...P}><path d="M20 40h24l-3-22H23z" /><path d="M14 40h36" /><path d="M22 34h20" /><rect x="29" y="31" width="6" height="6" /><path d="M46 50c-3-3-6 0-3 3 3 3 6 0 3-3zM46 50c3-3 6 0 3 3" /></g>;
const horns: G = () => <g {...P}><path d="M22 34c-8-4-10-14-6-20 2 8 6 10 12 12" /><path d="M42 34c8-4 10-14 6-20-2 8-6 10-12 12" /><circle cx="32" cy="38" r="8" /><circle cx="32" cy="38" r="2" /></g>;
const wisp: G = () => <g {...P}><path d="M32 12c8 10 12 16 12 24a12 12 0 0 1-24 0c0-6 4-10 6-14 2 6 4 8 6 8 0-6-2-12 0-18z" /><circle cx="18" cy="48" r="1.5" /><circle cx="46" cy="50" r="1.5" /></g>;
const lamp: G = () => <g {...P}><path d="M14 46h28c4 0 8-4 8-8H22" /><path d="M22 46c0 4 4 6 10 6s10-2 10-6" /><path d="M36 38c-2-6 6-8 4-14s6-8 4-12" /></g>;
const crescent: G = () => <g {...P}><path d="M38 14a18 18 0 1 0 0 36 14 14 0 1 1 0-36z" /><path d="M48 24c3 3 3 13 0 16M52 20c5 6 5 18 0 24" /></g>;
const flame: G = () => <g {...P}><path d="M32 10c10 12 14 20 14 28a14 14 0 0 1-28 0c0-8 6-12 8-18 2 6 6 8 6 8 2-6 0-12 0-18z" /><path d="M32 44a5 5 0 0 1-5-5c0-3 3-5 5-9 2 4 5 6 5 9a5 5 0 0 1-5 5z" /></g>;
const wave: G = () => <g {...P}><path d="M10 26c6-6 10-6 16 0s10 6 16 0 10-6 12-2" /><path d="M10 36c6-6 10-6 16 0s10 6 16 0 10-6 12-2" /><path d="M10 46c6-6 10-6 16 0s10 6 16 0 10-6 12-2" /></g>;
const swirl: G = () => <g {...P}><path d="M12 24h26a6 6 0 1 0-6-6" /><path d="M12 34h34a6 6 0 1 1-6 6" /><path d="M16 44h14" /></g>;
const crystal: G = () => <g {...P}><path d="M32 10l12 14-12 30-12-30z" /><path d="M20 24h24M32 10v44" /><path d="M14 52h36" /></g>;
const cap: G = () => <g {...P}><path d="M32 8l14 26H18z" /><path d="M16 34h32" /><path d="M20 34c0 12 6 20 12 20s12-8 12-20" /><circle cx="27" cy="40" r="1.5" /><circle cx="37" cy="40" r="1.5" /></g>;
const peaks: G = () => <g {...P}><path d="M8 50l16-28 10 16 6-10 16 22z" /><path d="M20 30l4 4 4-4" /><circle cx="44" cy="16" r="4" /></g>;
const note: G = () => <g {...P}><path d="M26 46V16l20-4v30" /><circle cx="21" cy="46" r="5" /><circle cx="41" cy="42" r="5" /><path d="M26 24l20-4" /></g>;
const tree: G = () => <g {...P}><path d="M32 54V30" /><path d="M32 10c10 0 16 8 14 16 4 4 2 12-6 12H24c-8 0-10-8-6-12-2-8 4-16 14-16z" /><path d="M32 40l-6-6M32 36l6-6" /></g>;
const foot: G = () => <g {...P}><path d="M24 54c-6 0-8-8-6-16s4-14 12-14 10 6 10 12-2 18-16 18z" /><circle cx="22" cy="16" r="3" /><circle cx="30" cy="12" r="3" /><circle cx="38" cy="14" r="3" /><circle cx="44" cy="20" r="2.5" /></g>;
const fox: G = () => <g {...P}><path d="M14 14l8 16M50 14l-8 16" /><path d="M14 14l10 6h16l10-6-4 22-14 14-14-14z" /><circle cx="26" cy="32" r="1.5" /><circle cx="38" cy="32" r="1.5" /><path d="M30 40h4" /></g>;
const feather: G = () => <g {...P}><path d="M48 12C28 14 18 30 16 52 34 46 46 34 48 12z" /><path d="M16 52l22-28M26 40h10M30 32h10" /></g>;
const serpent: G = () => <g {...P}><path d="M14 46c10 6 20-2 14-10s2-18 12-14 6 14 12 10" /><path d="M20 44l-2-6M30 34l4-4M42 24l2-6" /><circle cx="50" cy="32" r="1.5" /></g>;
const horn: G = () => <g {...P}><path d="M30 54l4-44 4 44" /><path d="M30 46h8M31 36h6M32 26h4" /></g>;
const crest: G = () => <g {...P}><path d="M32 10l18 8v14c0 12-8 18-18 22-10-4-18-10-18-22V18z" /><path d="M24 30h16M32 22v18" /></g>;
const golem: G = () => <g {...P}><rect x="18" y="14" width="28" height="34" rx="3" /><path d="M24 26h4M36 26h4" /><path d="M24 38h16" /><path d="M14 52h36" /></g>;
const eye: G = () => <g {...P}><path d="M8 32c8-12 40-12 48 0-8 12-40 12-48 0z" /><circle cx="32" cy="32" r="7" /><circle cx="32" cy="32" r="2" /><circle cx="32" cy="32" r="22" strokeDasharray="2 5" /></g>;
const ears: G = () => <g {...P}><path d="M10 22l14 8M54 22l-14 8" /><circle cx="32" cy="34" r="12" /><path d="M27 32l2 2M37 32l-2 2" /><path d="M28 40c2 2 6 2 8 0" /></g>;
const moon: G = () => <g {...P}><path d="M40 12a20 20 0 1 0 12 30 16 16 0 1 1-12-30z" /><path d="M18 50l4-4M24 54l2-6" /></g>;
const lotus: G = () => <g {...P}><path d="M32 48c-6-6-6-18 0-26 6 8 6 20 0 26z" /><path d="M32 48c-10-2-16-10-16-18 8 0 14 6 16 18zM32 48c10-2 16-10 16-18-8 0-14 6-16 18z" /><path d="M14 50h36" /></g>;
const lantern: G = () => <g {...P}><path d="M26 12h12M28 12v4M36 12v4" /><path d="M22 20h20v26H22z" /><path d="M22 28h20M22 38h20" /><path d="M28 50h8" /></g>;
const hex: G = () => <g {...P}><path d="M32 10l18 10v24L32 54 14 44V20z" /><circle cx="32" cy="32" r="6" /></g>;

const BY_KEY: Record<string, G> = {
  fairy: wings, pixie: wings, sprite: wings, flower_fairy: lotus, forest_fairy: tree, water_fairy: wave, light_fairy: wings,
  shadow_fairy: moon, court_fae: crest, brownie: cap, leprechaun: hat, clurichaun: hat, far_darrig: hat, puca: moon,
  aos_si: crest, sidhe: peaks, demon: horns, lesser_demon: horns, greater_demon: horns, oni: horns, div: horns, jinn: lamp, djinn: lamp,
  spirit: wisp, guardian_spirit: crest, trickster_spirit: moon, dream_spirit: moon, nature_spirit: tree, house_spirit: cap,
  place_spirit: peaks, astral_spirit: eye, shadow_spirit: moon, elemental_spirit: hex, will_o_wisp: wisp, ghost: wisp, wraith: wisp,
  banshee: crescent, salamander: flame, fire_elemental: flame, undine: wave, water_elemental: wave, naiad: wave, merfolk: wave,
  selkie: wave, sylph: swirl, air_elemental: swirl, gnome: crystal, earth_elemental: crystal, dwarf: crystal, kobold: crystal,
  tomte: cap, nisse: cap, gardstomte: cap, husande: cap, vittra: tree, vatte: tree, skogsra: tree, hulda: tree, dryad: tree, nymph: tree,
  nacken: note, gandharva: note, sjora: wave, bergsra: peaks, troll: peaks, jatte: peaks, giant: peaks, ogre: peaks,
  goblin: ears, hobgoblin: ears, dragon: serpent, griffin: feather, phoenix: feather, tengu: feather, unicorn: horn, sphinx: crest,
  centaur: crest, satyr: note, faun: note, werewolf: moon, vampiric_folklore: moon, shapeshifter: moon, golem: golem,
  sasquatch: foot, bigfoot: foot, yokai: lantern, kitsune: fox, huli_jing: fox, tanuki: fox, apsara: lotus, yaksha: lotus, peri: wings,
  astral_intelligence: eye, elf: leaf, high_elf: leaf, wood_elf: leaf, dark_elf: leaf, moon_elf: leaf, star_elf: leaf, craft_elf: leaf,
  rune_elf: leaf, wild_elf: leaf,
};
const BY_CATEGORY: Record<string, G> = { fae: wings, elves: leaf, leprechauns: hat, spirits: wisp, elementals: hex, nordic: cap,
  european: crest, cryptids: foot, asian: lantern, canon: eye, custom: hex };

export function Sigil({ species, name, size = 48 }: { species?: { key: string; name: string; category: string } | null; name?: string; size?: number }) {
  const cat = species?.category ?? "custom";
  const pal = PALETTE[cat] ?? PALETTE.custom;
  const tone = pal[hash(species?.key ?? name ?? "x") % pal.length];
  const glyph = (species && BY_KEY[species.key]) || BY_CATEGORY[cat] || hex;
  const label = `${name ?? "Agent"} — ${species?.name ?? "species not set"}`;
  return (
    <svg role="img" aria-label={label} width={size} height={size} viewBox="0 0 64 64" style={{ color: `var(--color-${tone})` }}
      className="shrink-0 rounded-full border border-line-strong bg-bg">
      <title>{label}</title>
      <circle cx="32" cy="32" r="30" fill="none" stroke="currentColor" strokeOpacity="0.25" strokeWidth="1" />
      <circle cx="32" cy="32" r="26" fill="none" stroke="currentColor" strokeOpacity="0.12" strokeWidth="6" />
      {glyph()}
    </svg>
  );
}

// ------------------------------------------------------------------------------------------------ evidence classes
const CLASS: Record<string, { icon: ReactNode; label: string; cls: string }> = {
  folklore: { icon: <ScrollText size={11} />, label: "Folklore", cls: "border-bronze/60 text-parchment" },
  fiction: { icon: <BookOpen size={11} />, label: "Fiction", cls: "border-series-1/50 text-series-1" },
  canon: { icon: <Sparkles size={11} />, label: "Demonkoncernen canon", cls: "border-violet/50 text-violet" },
  suggestion: { icon: <Lightbulb size={11} />, label: "Suggestion", cls: "border-cyan/50 text-cyan" },
  caution: { icon: <ShieldAlert size={11} />, label: "Cultural care", cls: "border-warning/50 text-warning" },
  user_request: { icon: <User size={11} />, label: "You asked", cls: "border-line-strong text-ink-2" },
  user_created: { icon: <Feather size={11} />, label: "User-created", cls: "border-gold/50 text-gold" },
  info: { icon: <Info size={11} />, label: "Note", cls: "border-line-strong text-ink-3" },
};
export function ClassLabel({ kind }: { kind: string }) {
  const c = CLASS[kind] ?? CLASS.info;
  return <span className={`inline-flex items-center gap-1 whitespace-nowrap rounded border px-1.5 py-px font-mono text-[10px] uppercase tracking-wider ${c.cls}`}>{c.icon}{c.label}</span>;
}

// ------------------------------------------------------------------------------------------------ cards
export const lc = (s?: string | null) => (s ?? "").toLowerCase();

export function SkillChip({ s }: { s: { name: string; level: string; basis: string; ai_generated?: boolean } }) {
  const verified = s.basis !== "assigned";
  return (
    <span className="inline-flex items-center gap-1 rounded border border-line px-1.5 py-px text-[11px] text-ink-2"
      title={`${s.level} — ${s.basis}${s.ai_generated ? ", AI-suggested" : ""}${verified ? "" : " (not verified)"}`}>
      {s.name}<span className="font-mono text-[9.5px] text-ink-3">{s.level === "Unverified" ? "unverified" : `${s.level.toLowerCase()} · ${s.basis}`}</span>
    </span>
  );
}

export function AgentCard({ a }: { a: any }) {
  return (
    <article className="flex min-w-0 flex-col gap-2 rounded-lg border border-line bg-surface p-3" data-testid="agent-card">
      <div className="flex items-start gap-3">
        <Sigil species={a.species} name={a.persona_name} />
        <div className="min-w-0 flex-1">
          <Link href={`/personnel/${a.id}`} className="block font-serif text-[15px] font-semibold leading-snug text-ink hover:text-violet [overflow-wrap:anywhere]">{a.display}</Link>
          <div className="text-[12px] text-ink-3 [overflow-wrap:anywhere]">{a.title} · {a.rank}{a.department ? ` · ${a.department.name}` : ""}</div>
        </div>
      </div>
      <p className="line-clamp-2 text-[12.5px] text-ink-2">{a.purpose || a.description}</p>
      <div className="flex flex-wrap items-center gap-1.5">
        <StatusBadge status={lc(a.lifecycle)} />
        <StatusBadge status={a.observation?.state ?? "unknown"} />
        {a.custom && <ClassLabel kind="user_created" />}
        {a.species?.key && <Link href={`/bestiary/${a.species.key}`} className="text-[11px] text-ink-3 underline decoration-dotted hover:text-violet">about the {a.species.name}</Link>}
      </div>
      {a.skills?.length > 0 && <div className="flex flex-wrap gap-1">{a.skills.slice(0, 3).map((s: any) => <SkillChip key={s.name} s={s} />)}</div>}
      <div className="mt-auto flex flex-wrap gap-x-3 gap-y-1 text-[11px] text-ink-3">
        {a.supervisor && <span>reports to <Link className="underline decoration-dotted hover:text-violet" href={`/personnel/${a.supervisor.id}`}>{a.supervisor.name}</Link></span>}
        <span>latest mission: {a.latest_mission ? `${a.latest_mission.type} (${a.latest_mission.status})` : "none yet"}</span>
        {a.achievements?.length > 0 && <span className="text-gold">★ {a.achievements[a.achievements.length - 1]}</span>}
      </div>
    </article>
  );
}

// ------------------------------------------------------------------------------------------------ G-SUS proposal card
/** The interactive proposal G-SUS makes in chat. Approving calls the REAL creation endpoint (the same pipeline as the
 *  Bestiary and Personnel); nothing is created before that. */
export function ProposalCard({ proposal, runId, canCreate }: { proposal: any; runId: number; canCreate: boolean }) {
  const [i, setI] = useState(0);
  const base = proposal.proposals[i]?.spec;
  const [spec, setSpec] = useState<any>(base);
  const [choice, setChoice] = useState<string>(proposal.duplicates?.some((d: any) => d.score >= 0.35) ? "" : "new");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [done, setDone] = useState<any>(null);
  const [cancelled, setCancelled] = useState(false);
  const recs: any[] = proposal.species_recommendations ?? [];
  if (cancelled) return <div className="rounded-md border border-line px-3 py-2 text-[12.5px] text-ink-3">Proposal dismissed — nothing was created.</div>;
  const pick = (n: number) => { setI(n); setSpec(proposal.proposals[n].spec); };
  const create = async () => {
    setBusy(true); setErr(null);
    try {
      setDone(await api("/api/personnel/agents", { method: "POST", json: { spec, source: "GSUS_CHAT", gsus_run_id: runId, duplicate_choice: choice || null } }));
    } catch (e) { setErr(readError(e)); } finally { setBusy(false); }
  };
  const edit = () => {
    try { sessionStorage.setItem("rocky.creator.handoff", JSON.stringify({ spec, source: "GSUS_CHAT", run: runId })); } catch { /* storage unavailable */ }
    window.location.href = `/personnel/create?source=GSUS_CHAT&from=gsus&run=${runId}`;
  };
  if (done) {
    return (
      <div role="status" className="rounded-lg border border-good/40 bg-good/10 p-3 text-[13px]">
        {done.message} {done.agent?.id && <Link className="underline" href={`/personnel/${done.agent.id}`}>Open profile</Link>}
        {done.approval_id && <> · <Link className="underline" href={`/approvals?id=${done.approval_id}`}>approval #{done.approval_id}</Link></>}
      </div>
    );
  }
  const species = recs.find((r) => r.key === spec.species_key) ?? { key: spec.species_key, name: spec.species_key, category: "custom" };
  return (
    <section aria-label="Agent proposal" data-testid="proposal-card" className="rounded-lg border border-violet/40 bg-surface p-4">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <div className="font-mono text-[11px] uppercase tracking-[0.16em] text-violet">Agent proposal · {proposal.method === "model" ? `AI design (${proposal.model})` : "rules (no model)"}</div>
        {proposal.proposals.length > 1 && <div className="flex gap-1">{proposal.proposals.map((p: any, n: number) =>
          <button key={n} onClick={() => pick(n)} aria-pressed={n === i} className={`rounded border px-2 py-0.5 text-[11px] ${n === i ? "border-violet text-violet" : "border-line text-ink-3"}`}>{p.spec.persona_name}</button>)}</div>}
      </div>
      <div className="flex items-start gap-3">
        <Sigil species={species} name={spec.persona_name} size={56} />
        <div className="min-w-0 flex-1 space-y-2">
          <div className="grid gap-2 sm:grid-cols-2">
            <label className="text-[11px] text-ink-3">Name<input className="mt-0.5 w-full" value={spec.persona_name} onChange={(e) => setSpec({ ...spec, persona_name: e.target.value })} /></label>
            <label className="text-[11px] text-ink-3">Species
              <select className="mt-0.5 w-full" value={spec.species_key} onChange={(e) => setSpec({ ...spec, species_key: e.target.value })}>
                {[...new Map([[spec.species_key, species], ...recs.map((r) => [r.key, r] as [string, any])]).values()].map((r: any) => <option key={r.key} value={r.key}>{r.name}</option>)}
              </select></label>
          </div>
          <div className="text-[13px] text-ink-2">{spec.purpose}</div>
          <div className="text-[12px] text-ink-3">Specializations: {spec.specializations.join(", ")} · Personality: {spec.traits.join(", ") || "—"}</div>
          {spec.skills?.length > 0 && <div className="flex flex-wrap gap-1">{spec.skills.slice(0, 6).map((s: any) => <SkillChip key={s.name} s={s} />)}</div>}
        </div>
      </div>
      {recs.length > 0 && (
        <details className="mt-3 text-[12px]"><summary className="cursor-pointer text-ink-2">Why these species? (folklore, canon and suggestions kept apart)</summary>
          <ul className="mt-2 space-y-2">{recs.slice(0, 3).map((r) => (
            <li key={r.key}><Link href={`/bestiary/${r.key}`} className="font-semibold text-ink underline decoration-dotted">{r.name}</Link>
              <ul className="mt-1 space-y-1">{r.reasons.map((x: any, n: number) => <li key={n} className="flex flex-wrap items-start gap-1.5"><ClassLabel kind={x.class} /><span className="text-ink-2">{x.text}</span></li>)}</ul></li>))}</ul>
        </details>
      )}
      {proposal.duplicates?.length > 0 && (
        <fieldset className="mt-3 rounded-md border border-warning/40 p-2 text-[12.5px]">
          <legend className="px-1 text-warning">Similar agents already exist</legend>
          <ul className="mb-2 space-y-1">{proposal.duplicates.slice(0, 3).map((d: any) => <li key={d.agent.id}><Link className="underline" href={`/personnel/${d.agent.id}`}>{d.agent.display}</Link> <span className="num text-ink-3">{d.score.toFixed(2)} → {d.recommendation.replace("_", " ")}</span></li>)}</ul>
          <div className="flex flex-wrap gap-3">{["use_existing", "extend", "complement", "new"].map((c) => (
            <label key={c} className="inline-flex items-center gap-1"><input type="radio" name={`dup-${runId}`} checked={choice === c} onChange={() => setChoice(c)} />{c.replace("_", " ")}</label>))}</div>
        </fieldset>
      )}
      <ErrorBanner error={err} />
      <div className="mt-3 flex flex-wrap gap-2">
        {canCreate ? <Button variant="primary" busy={busy} disabled={!choice && proposal.duplicates?.some((d: any) => d.score >= 0.35)} onClick={create}>Approve &amp; create</Button>
          : <span className="text-[12px] text-ink-3">Creating agents needs the agent.develop permission.</span>}
        <Button onClick={edit}>Edit in the Agent Creator</Button>
        <Button onClick={() => setCancelled(true)}>Cancel</Button>
      </div>
      <p className="mt-2 text-[11px] text-ink-3">Starts at permission level 1; tools are suggestions until governance grants them; skills stay unverified until tested.</p>
    </section>
  );
}

/** API errors from the creator carry {message, errors:[{field, message}]} as JSON in the message. */
export function readError(e: unknown): string {
  const m = (e as Error)?.message ?? String(e);
  try {
    const j = JSON.parse(m);
    return [j.message, ...(j.errors ?? []).map((x: any) => `${x.field}: ${x.message}`)].filter(Boolean).join(" · ");
  } catch { return m; }
}
export function fieldErrors(e: unknown): Record<string, string> {
  try { return Object.fromEntries((JSON.parse((e as Error).message).errors ?? []).map((x: any) => [x.field, x.message])); } catch { return {}; }
}

// ------------------------------------------------------------------------------------------------ form helpers
export function ChipPicker({ label, options, value, onChange, max = 12 }: { label: string; options: string[]; value: string[]; onChange: (v: string[]) => void; max?: number }) {
  const toggle = (o: string) => onChange(value.includes(o) ? value.filter((x) => x !== o) : value.length >= max ? value : [...value, o]);
  return (
    <fieldset>
      <legend className="mb-1 text-[11px] text-ink-3">{label}{max < 99 ? ` (up to ${max})` : ""}</legend>
      <div className="flex flex-wrap gap-1.5">{options.map((o) => (
        <button key={o} type="button" aria-pressed={value.includes(o)} onClick={() => toggle(o)}
          className={`rounded-full border px-2.5 py-1 text-[12px] pointer-coarse:min-h-9 ${value.includes(o) ? "border-violet bg-violet/15 text-violet" : "border-line text-ink-2 hover:border-line-strong"}`}>{o}</button>))}</div>
    </fieldset>
  );
}

/** One entry per line ↔ string[] (tasks, limits, goals…). */
export function LinesField({ label, value, onChange, rows = 3, placeholder, error }: { label: string; value: string[]; onChange: (v: string[]) => void; rows?: number; placeholder?: string; error?: string }) {
  const [text, setText] = useState(value.join("\n"));
  // an outside change (AI fill, reset) replaces the text; the person's own typing never does
  if (text.split("\n").map((l) => l.trim()).filter(Boolean).join("\n") !== value.join("\n")) setText(value.join("\n"));
  return (
    <label className="block text-[11px] text-ink-3">{label} <span className="text-ink-3">(one per line)</span>
      <textarea rows={rows} className="mt-0.5 w-full" value={text} placeholder={placeholder} aria-invalid={!!error}
        onChange={(e) => { setText(e.target.value); onChange(e.target.value.split("\n").map((l) => l.trim()).filter(Boolean)); }} />
      {error && <span className="text-warning">{error}</span>}
    </label>
  );
}

export function SkillsEditor({ value, onChange, levels }: { value: any[]; onChange: (v: any[]) => void; levels: string[] }) {
  const [name, setName] = useState("");
  const add = () => { const n = name.trim(); if (n && !value.some((s) => s.name.toLowerCase() === n.toLowerCase())) onChange([...value, { name: n, level: "Unverified", basis: "assigned", ai_generated: false }]); setName(""); };
  return (
    <div>
      <ul className="space-y-1.5" aria-label="Skills">{value.map((s, i) => (
        <li key={s.name} className="flex flex-wrap items-center gap-2 text-[13px]">
          <span className="min-w-[10rem] text-ink">{s.name}</span>
          <select aria-label={`Level for ${s.name}`} value={s.level} onChange={(e) => onChange(value.map((x, j) => j === i ? { ...x, level: e.target.value } : x))}>
            {levels.map((l) => <option key={l}>{l}</option>)}</select>
          <span className="font-mono text-[10.5px] text-ink-3">{s.basis}{s.ai_generated ? " · AI-suggested" : ""}{s.basis === "assigned" ? " · not verified" : ""}</span>
          <button type="button" className="text-[12px] text-ink-3 underline hover:text-ink" onClick={() => onChange(value.filter((_, j) => j !== i))} aria-label={`Remove ${s.name}`}>remove</button>
        </li>))}</ul>
      <div className="mt-2 flex gap-2"><input aria-label="New skill" placeholder="Add a skill (e.g. Python)" value={name} onChange={(e) => setName(e.target.value)}
        onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); add(); } }} /><Button onClick={add}>Add skill</Button></div>
      <p className="mt-1 text-[11px] text-ink-3">Levels you choose are <em>assigned</em>. They are shown as unverified until a test or measured performance says otherwise — choosing “Expert” does not make an agent an expert.</p>
    </div>
  );
}

/** Onboarding capability checks: pass / fail / skipped — skipped is never counted as passed. */
export function Tests({ t }: { t: any }) {
  if (!t) return <p className="mt-2 text-[12px] text-ink-3">No onboarding tests recorded (code agents are verified by the test suite; run a capability test to record one).</p>;
  return (
    <details className="mt-3 text-[12.5px]" open>
      <summary className="cursor-pointer text-ink-2">Capability checks: {t.passed} passed · {t.failed} failed · {t.skipped} skipped {t.model ? `(model ${t.model})` : "(no model)"}</summary>
      <ul className="mt-1 space-y-0.5">{t.results.map((r: any) => <li key={r.id} className="flex flex-wrap items-center gap-1.5"><StatusBadge status={r.status} /><span>{r.name}</span><span className="text-[11px] text-ink-3">{r.kind} · {r.detail}</span></li>)}</ul>
      <p className="mt-1 text-[11px] text-ink-3">{t.basis}. {t.note}</p>
    </details>
  );
}

