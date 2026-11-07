"use client";
/** THE BESTIARY — Demonkoncernen's encyclopedia of beings, races and specializations. A knowledge area of its own,
 *  separate from the personnel register but linked to it both ways. Folklore, fiction and system canon are labelled
 *  apart; inspiration, never limits. */
import Link from "next/link";
import { Suspense, useState } from "react";
import { useSearchParams } from "next/navigation";
import { ClassLabel, Sigil, readError } from "@/components/personnel";
import { Button, Card, Empty, ErrorBanner, PageHeader } from "@/components/ui";
import { api } from "@/lib/api";
import { useApi, useMe } from "@/lib/hooks";

function Bestiary() {
  const params = useSearchParams();
  const [tab, setTab] = useState<"beings" | "specializations">(params.get("tab") === "specializations" ? "specializations" : "beings");
  const me = useMe();
  const canEdit = !!me?.permissions?.includes("agent.develop");
  return (
    <div>
      <PageHeader title="The Bestiary" kicker="Encyclopedia of the astral world">
        <Link href="/personnel" className="text-[13px] text-ink-2 underline decoration-dotted hover:text-violet">← Personnel register</Link>
      </PageHeader>
      <p className="mb-4 max-w-3xl text-[13px] text-ink-2">Beings, traditions, behaviours and specializations. Every entry keeps <ClassLabel kind="folklore" /> (a summary of traditional belief), <ClassLabel kind="fiction" /> and <ClassLabel kind="canon" /> apart, with sources as further reading. A race never limits what an agent can do — a fairy can run the backend and a demon can be a botanist.</p>
      <div role="tablist" aria-label="Bestiary sections" className="mb-4 flex gap-1">
        {(["beings", "specializations"] as const).map((t) => (
          <button key={t} role="tab" aria-selected={tab === t} onClick={() => setTab(t)}
            className={`rounded-md border px-3 py-1.5 text-[13px] pointer-coarse:min-h-10 ${tab === t ? "border-violet text-violet" : "border-line text-ink-2"}`}>{t === "beings" ? "Beings & races" : "Specializations"}</button>))}
      </div>
      {tab === "beings" ? <Beings canEdit={canEdit} /> : <Specializations />}
    </div>
  );
}

function Beings({ canEdit }: { canEdit: boolean }) {
  const [q, setQ] = useState("");
  const [category, setCategory] = useState("");
  const [origin, setOrigin] = useState("");
  const [kind, setKind] = useState("");
  const qs = new URLSearchParams(Object.entries({ q, category, origin, kind }).filter(([, v]) => v)).toString();
  const list = useApi<any>(`/api/bestiary?${qs}`, [qs]);
  const d = list.data;
  return (
    <div>
      <Card>
        <form role="search" className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4" onSubmit={(e) => e.preventDefault()}>
          <label className="text-[11px] text-ink-3">Search names and alternative names<input type="search" className="mt-0.5 w-full" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Sidhe, bean sí, nøkken…" /></label>
          <label className="text-[11px] text-ink-3">Type of being<select className="mt-0.5 w-full" value={category} onChange={(e) => setCategory(e.target.value)}>
            <option value="">All types</option>{d?.categories.map((c: any) => <option key={c.key} value={c.key}>{c.name} ({c.count})</option>)}</select></label>
          <label className="text-[11px] text-ink-3">Cultural origin<select className="mt-0.5 w-full" value={origin} onChange={(e) => setOrigin(e.target.value)}>
            <option value="">All origins</option>{d?.origins.map((o: string) => <option key={o}>{o}</option>)}</select></label>
          <label className="text-[11px] text-ink-3">Entry<select className="mt-0.5 w-full" value={kind} onChange={(e) => setKind(e.target.value)}>
            <option value="">Beings and categories</option><option value="being">Beings</option><option value="category">Broad categories (e.g. Yōkai)</option></select></label>
        </form>
      </Card>
      <ErrorBanner error={list.error} />
      <div className="my-3 text-[12px] text-ink-3">{d ? `${d.species.length} of ${d.total} entries` : "Opening the Bestiary…"}</div>
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {d?.species.map((s: any) => (
          <article key={s.key} className="flex min-w-0 gap-3 rounded-lg border border-line bg-surface p-3" data-testid="being-card">
            <Sigil species={s} name={s.name} />
            <div className="min-w-0">
              <Link href={`/bestiary/${s.key}`} className="font-serif text-[15px] font-semibold text-ink hover:text-violet">{s.name}</Link>
              <div className="text-[11.5px] text-ink-3">{s.origin}{s.kind === "category" ? " · broad category" : ""}{s.alt_names.length ? ` · ${s.alt_names.slice(0, 2).join(", ")}` : ""}</div>
              <p className="mt-1 line-clamp-3 text-[12.5px] text-ink-2">{s.summary}</p>
              <div className="mt-1.5 flex flex-wrap items-center gap-1">
                {s.has.folklore && <ClassLabel kind="folklore" />}{s.has.fiction && <ClassLabel kind="fiction" />}{s.has.canon && <ClassLabel kind="canon" />}
                {s.user_created && <ClassLabel kind="user_created" />}
                {s.agents > 0 && <Link href={`/personnel?species=${s.key}`} className="text-[11px] text-cyan underline">{s.agents} in service</Link>}
              </div>
            </div>
          </article>))}
      </div>
      {d && !d.species.length && <Card><Empty title="No being matches">Try another spelling or an alternative name.</Empty></Card>}
      {canEdit && <AddBeing onAdded={list.reload} />}
    </div>
  );
}

function AddBeing({ onAdded }: { onAdded: () => void }) {
  const [f, setF] = useState({ name: "", origin: "", canon: "", fiction: "", folklore: "", source_title: "", source_author: "", traits: "" });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [ok, setOk] = useState<string | null>(null);
  const set = (k: string, v: string) => setF((x) => ({ ...x, [k]: v }));
  const add = async () => {
    setBusy(true); setErr(null); setOk(null);
    try {
      const r = await api<any>("/api/bestiary", { method: "POST", json: { name: f.name, origin: f.origin || "User-created", canon: f.canon, fiction: f.fiction,
        folklore: f.folklore, traits: f.traits.split(",").map((x) => x.trim()).filter(Boolean),
        sources: f.source_title ? [{ title: f.source_title, author: f.source_author, year: "", class: "folklore collection" }] : [] } });
      setOk(`Added ${r.name}.`); setF({ name: "", origin: "", canon: "", fiction: "", folklore: "", source_title: "", source_author: "", traits: "" }); onAdded();
    } catch (e) { setErr(readError(e)); } finally { setBusy(false); }
  };
  return (
    <Card title="Add a being (controlled data entry)" className="mt-6">
      <div className="grid gap-2 sm:grid-cols-2">
        <label className="text-[11px] text-ink-3">Name<input className="mt-0.5 w-full" value={f.name} onChange={(e) => set("name", e.target.value)} /></label>
        <label className="text-[11px] text-ink-3">Cultural origin<input className="mt-0.5 w-full" value={f.origin} onChange={(e) => set("origin", e.target.value)} placeholder="User-created" /></label>
        <label className="text-[11px] text-ink-3 sm:col-span-2">Demonkoncernen canon (your own fiction)<textarea rows={2} className="mt-0.5 w-full" value={f.canon} onChange={(e) => set("canon", e.target.value)} /></label>
        <label className="text-[11px] text-ink-3 sm:col-span-2">Fiction (modern books, art, games)<textarea rows={2} className="mt-0.5 w-full" value={f.fiction} onChange={(e) => set("fiction", e.target.value)} /></label>
        <label className="text-[11px] text-ink-3 sm:col-span-2">Folklore summary — needs a source<textarea rows={2} className="mt-0.5 w-full" value={f.folklore} onChange={(e) => set("folklore", e.target.value)} /></label>
        <label className="text-[11px] text-ink-3">Source title<input className="mt-0.5 w-full" value={f.source_title} onChange={(e) => set("source_title", e.target.value)} /></label>
        <label className="text-[11px] text-ink-3">Source author<input className="mt-0.5 w-full" value={f.source_author} onChange={(e) => set("source_author", e.target.value)} /></label>
        <label className="text-[11px] text-ink-3 sm:col-span-2">Traits (comma-separated)<input className="mt-0.5 w-full" value={f.traits} onChange={(e) => set("traits", e.target.value)} /></label>
      </div>
      <ErrorBanner error={err} />
      {ok && <div role="status" className="mt-2 text-[12.5px] text-good">{ok}</div>}
      <div className="mt-2"><Button variant="primary" busy={busy} disabled={f.name.trim().length < 2} onClick={add}>Add to The Bestiary</Button></div>
      <p className="mt-1 text-[11px] text-ink-3">Entries added here are marked user-created. No code change is needed for new beings.</p>
    </Card>
  );
}

function Specializations() {
  const s = useApi<any>("/api/specializations");
  const [q, setQ] = useState("");
  const rows = (s.data?.specializations ?? []).filter((x: any) => !q || `${x.name} ${x.description} ${(x.keywords ?? []).join(" ")}`.toLowerCase().includes(q.toLowerCase()));
  return (
    <div>
      <ErrorBanner error={s.error} />
      <div className="mb-3 flex flex-wrap items-end justify-between gap-2">
        <label className="text-[11px] text-ink-3">Search specializations<input type="search" className="mt-0.5 block" value={q} onChange={(e) => setQ(e.target.value)} /></label>
        <span className="text-[12px] text-ink-3">{s.data?.note}</span>
      </div>
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {rows.map((x: any) => (
          <Card key={x.key} title={x.name} action={x.user_created ? <ClassLabel kind="user_created" /> : undefined}>
            <p className="text-[12.5px] text-ink-2">{x.description}</p>
            <dl className="mt-2 space-y-1 text-[12px]">
              {x.competencies?.length > 0 && <div><dt className="inline text-ink-3">Competencies: </dt><dd className="inline">{x.competencies.join(", ")}</dd></div>}
              {x.tools?.length > 0 && <div><dt className="inline text-ink-3">Tools (Tool Gateway): </dt><dd className="inline font-mono text-[11.5px]">{x.tools.join(", ")}</dd></div>}
              {x.department_names?.length > 0 && <div><dt className="inline text-ink-3">Departments: </dt><dd className="inline">{x.department_names.join(", ")}</dd></div>}
              {x.example_tasks?.length > 0 && <div><dt className="inline text-ink-3">Example: </dt><dd className="inline">{x.example_tasks[0]}</dd></div>}
            </dl>
            <div className="mt-2 text-[12px]"><span className="text-ink-3">In service ({x.agent_count}): </span>{x.agents.length ? x.agents.map((a: any, i: number) => <span key={a.id}>{i ? " · " : ""}<Link className="underline decoration-dotted" href={`/personnel/${a.id}`}>{a.display}</Link></span>) : "nobody yet"}</div>
            {x.species_suggesting?.length > 0 && <div className="mt-1 text-[11.5px] text-ink-3">Beings whose entries suggest it: {x.species_suggesting.map((b: any) => b.name).join(", ")} — a suggestion, never a requirement.</div>}
          </Card>))}
      </div>
    </div>
  );
}

export default function Page() {
  return <Suspense><Bestiary /></Suspense>;
}
