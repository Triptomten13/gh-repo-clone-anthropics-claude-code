"use client";
/** A Bestiary article. Folklore, fiction, Demonkoncernen canon and cultural care are separate, labelled sections;
 *  sources are further reading (the text is a summary, not a quotation). Links to the registered agents of this race
 *  and opens the Custom Agent Creator with the race preselected. */
import Link from "next/link";
import { use, useState } from "react";
import { Wand2 } from "lucide-react";
import { AgentCard, ClassLabel, Sigil, readError } from "@/components/personnel";
import { Button, Card, Empty, ErrorBanner, PageHeader } from "@/components/ui";
import { api } from "@/lib/api";
import { useApi, useMe } from "@/lib/hooks";

export default function Article({ params }: { params: Promise<{ key: string }> }) {
  const { key } = use(params);
  const a = useApi<any>(`/api/bestiary/${key}`, [key]);
  const me = useMe();
  const canEdit = !!me?.permissions?.includes("agent.develop");
  const [editing, setEditing] = useState(false);
  const s = a.data;
  if (!s) return a.error ? <ErrorBanner error={a.error} /> : <div className="text-ink-3">Opening the article…</div>;
  const list = (label: string, xs: string[]) => xs?.length ? <div><dt className="text-ink-3">{label}</dt><dd className="text-ink-2">{xs.join(", ")}</dd></div> : null;
  return (
    <div>
      <div className="mb-2 text-[12px] text-ink-3"><Link href="/bestiary" className="underline decoration-dotted">The Bestiary</Link> / {s.name}</div>
      <div className="mb-6 flex flex-wrap items-start gap-4">
        <Sigil species={s} name={s.name} size={88} />
        <div className="min-w-0 flex-1">
          <PageHeader title={s.name} kicker={`${s.origin}${s.kind === "category" ? " · broad category" : ""}`}>
            {s.kind === "being" && <Link href={s.create_link} className="inline-flex items-center gap-1.5 rounded-md bg-violet px-3 py-1.5 text-[13px] font-semibold text-black hover:brightness-110 pointer-coarse:min-h-10" data-testid="create-from-species">
              <Wand2 size={14} /> Create {/^[aeiou]/i.test(s.name) ? "an" : "a"} {s.name} agent</Link>}
          </PageHeader>
          {s.alt_names?.length > 0 && <p className="-mt-3 text-[12.5px] text-ink-3">Also known as: {s.alt_names.join(", ")}</p>}
          {s.user_created && <p className="mt-1"><ClassLabel kind="user_created" /></p>}
        </div>
      </div>
      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_320px]">
        <div className="space-y-4">
          {s.folklore && <Card title={<span className="inline-flex items-center gap-2"><ClassLabel kind="folklore" /> Traditional belief</span>}><p className="font-serif text-[14.5px] leading-relaxed text-ink">{s.folklore}</p></Card>}
          {s.fiction && <Card title={<span className="inline-flex items-center gap-2"><ClassLabel kind="fiction" /> In modern fiction</span>}><p className="font-serif text-[14px] leading-relaxed text-ink-2">{s.fiction}</p></Card>}
          {s.canon && <Card title={<span className="inline-flex items-center gap-2"><ClassLabel kind="canon" /> Demonkoncernen canon</span>}><p className="font-serif text-[14px] leading-relaxed text-ink-2">{s.canon}</p></Card>}
          {s.caution && <div role="note" className="rounded-lg border border-warning/40 bg-warning/5 p-3 text-[13px] text-ink-2"><ClassLabel kind="caution" /> <span className="ml-1">{s.caution}</span></div>}
          {!s.folklore && !s.fiction && !s.canon && <Card><Empty title="No text yet">This entry has a name but no article text.</Empty></Card>}
          <Card title={`Registered agents of this race (${s.agents.length})`}>
            {s.agents.length ? <div className="grid gap-3 md:grid-cols-2">{s.agents.map((x: any) => <AgentCard key={x.id} a={x} />)}</div>
              : <Empty title="Nobody of this race works here yet">{s.kind === "being" && <Link className="text-violet underline" href={s.create_link}>Summon the first one</Link>}</Empty>}
          </Card>
        </div>
        <aside className="space-y-4">
          <Card title="At a glance">
            <dl className="space-y-1.5 text-[12.5px]">
              {list("Traits", s.traits)}{list("Abilities", s.abilities)}{list("Strengths", s.strengths)}{list("Weaknesses", s.weaknesses)}
              {s.symbolism && <div><dt className="text-ink-3">Symbolism</dt><dd className="text-ink-2">{s.symbolism}</dd></div>}
              {list("Example roles", s.example_roles)}
            </dl>
            <p className="mt-2 text-[11px] text-ink-3">Fictional character colour in this system — not universal to every tradition, and never a permission.</p>
          </Card>
          {s.possible_specializations?.length > 0 && <Card title="Possible specializations">
            <ul className="flex flex-wrap gap-1.5">{s.possible_specializations.map((x: any) => <li key={x.key}><Link href={`/personnel?specialization=${x.key}`} className="rounded border border-cyan/40 px-1.5 py-px text-[12px] text-cyan">{x.name}</Link></li>)}</ul>
            <p className="mt-2 text-[11px] text-ink-3">Inspiration, not limits — any race can take any specialization.</p></Card>}
          {(s.subtype_articles?.length > 0 || s.subtypes?.length > 0 || s.related?.length > 0) && <Card title="Related">
            {s.subtypes?.length > 0 && <div className="text-[12.5px]"><span className="text-ink-3">Kinds: </span>{s.subtypes.map((t: string, i: number) => {
              const art = s.subtype_articles.find((x: any) => x.key === t);
              return <span key={t}>{i ? ", " : ""}{art ? <Link className="underline decoration-dotted" href={`/bestiary/${t}`}>{art.name}</Link> : t}</span>;
            })}</div>}
            {s.related?.length > 0 && <ul className="mt-2 space-y-0.5 text-[12.5px]">{s.related.map((r: any) => <li key={r.key}><span className="font-mono text-[10.5px] text-ink-3">{r.type.replace("_", " ")}</span> <Link className="underline decoration-dotted" href={`/bestiary/${r.key}`}>{r.name}</Link></li>)}</ul>}
          </Card>}
          <Card title="Sources — further reading">
            {s.sources?.length ? <ul className="space-y-1.5 text-[12.5px]">{s.sources.map((x: any, i: number) => <li key={i}><span className="text-ink">{x.author ? `${x.author}, ` : ""}<em>{x.title}</em>{x.year ? ` (${x.year})` : ""}</span> <span className="font-mono text-[10px] text-ink-3">{x.class}</span></li>)}</ul>
              : <p className="text-[12.5px] text-ink-3">No source recorded.</p>}
            <p className="mt-2 text-[11px] text-ink-3">The article text is our summary, not a quotation from these works.</p>
          </Card>
          {canEdit && <Card title="Edit entry">{editing ? <Editor s={s} onDone={() => { setEditing(false); a.reload(); }} /> : <Button onClick={() => setEditing(true)}>Edit canon, fiction & traits</Button>}</Card>}
        </aside>
      </div>
    </div>
  );
}

function Editor({ s, onDone }: { s: any; onDone: () => void }) {
  const [f, setF] = useState({ canon: s.canon ?? "", fiction: s.fiction ?? "", traits: (s.traits ?? []).join(", "), example_roles: (s.example_roles ?? []).join(", "), caution: s.caution ?? "" });
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const split = (x: string) => x.split(",").map((y) => y.trim()).filter(Boolean);
  const save = async () => {
    setBusy(true); setErr(null);
    try { await api(`/api/bestiary/${s.key}`, { method: "PATCH", json: { canon: f.canon, fiction: f.fiction, traits: split(f.traits), example_roles: split(f.example_roles), caution: f.caution } }); onDone(); }
    catch (e) { setErr(readError(e)); } finally { setBusy(false); }
  };
  return (
    <div className="space-y-2">
      <label className="block text-[11px] text-ink-3">Demonkoncernen canon<textarea rows={3} className="mt-0.5 w-full" value={f.canon} onChange={(e) => setF({ ...f, canon: e.target.value })} /></label>
      <label className="block text-[11px] text-ink-3">Fiction<textarea rows={2} className="mt-0.5 w-full" value={f.fiction} onChange={(e) => setF({ ...f, fiction: e.target.value })} /></label>
      <label className="block text-[11px] text-ink-3">Traits<input className="mt-0.5 w-full" value={f.traits} onChange={(e) => setF({ ...f, traits: e.target.value })} /></label>
      <label className="block text-[11px] text-ink-3">Example roles<input className="mt-0.5 w-full" value={f.example_roles} onChange={(e) => setF({ ...f, example_roles: e.target.value })} /></label>
      <label className="block text-[11px] text-ink-3">Cultural care note<textarea rows={2} className="mt-0.5 w-full" value={f.caution} onChange={(e) => setF({ ...f, caution: e.target.value })} /></label>
      <ErrorBanner error={err} />
      <Button variant="primary" busy={busy} onClick={save}>Save (audited)</Button>
      <p className="text-[11px] text-ink-3">The folklore summary is changed through the API together with its sources, so traditional belief is never edited without a reference.</p>
    </div>
  );
}
