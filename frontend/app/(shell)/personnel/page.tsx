"use client";
/** PERSONNEL — Demonkoncernen's one shared register. Every agent appears here together, whatever its race; filters
 *  narrow the list, nothing groups agents by race. Departments are functional. */
import Link from "next/link";
import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Plus } from "lucide-react";
import { AgentCard, Sigil, lc } from "@/components/personnel";
import { Button, Card, Empty, ErrorBanner, PageHeader, Stat, StatusBadge } from "@/components/ui";
import { useApi, useMe, useRefreshOn } from "@/lib/hooks";

type View = "cards" | "hierarchy" | "departments";

function Personnel() {
  const params = useSearchParams();
  const router = useRouter();
  const me = useMe();
  const canCreate = !!me?.permissions?.includes("agent.develop");
  const [q, setQ] = useState(params.get("q") ?? "");
  const [f, setF] = useState({ department: params.get("department") ?? "", specialization: params.get("specialization") ?? "",
    species: params.get("species") ?? "", status: params.get("status") ?? "", sort: params.get("sort") ?? "name" });
  const [view, setView] = useState<View>((params.get("view") as View) || "cards");
  const qs = new URLSearchParams(Object.entries({ q, ...f }).filter(([, v]) => v)).toString();
  const list = useApi<any>(`/api/personnel?${qs}`, [qs]);
  useRefreshOn(["task"], list.reload);
  useEffect(() => { router.replace(`/personnel?${qs}${view !== "cards" ? `${qs ? "&" : ""}view=${view}` : ""}`, { scroll: false }); }, [qs, view, router]);
  const facets = list.data?.facets;
  const agents: any[] = list.data?.agents ?? [];
  const set = (k: string, v: string) => setF((p) => ({ ...p, [k]: v }));
  const active = agents.filter((a) => a.lifecycle === "ACTIVE").length;

  return (
    <div>
      <PageHeader title="Personnel" kicker="Demonkoncernen · one shared register">
        <Link href="/bestiary" className="text-[13px] text-ink-2 underline decoration-dotted hover:text-violet">The Bestiary →</Link>
        {canCreate && <Link href="/personnel/create?source=PERSONNEL" className="inline-flex items-center gap-1.5 rounded-md bg-violet px-3 py-1.5 text-[13px] font-semibold text-black hover:brightness-110 pointer-coarse:min-h-10"><Plus size={14} /> CREATE NEW AGENT</Link>}
      </PageHeader>
      <p className="mb-4 max-w-3xl text-[13px] text-ink-2">Demons, djinn, spirits, fairies, elves, Leprechauns, Sasquatch and every other being work side by side, organised by what they do — never by race. Each agent is shown as <span className="text-ink">Name · Race · Specialization</span>. Race, rank and personality are identity; access comes only from governance.</p>
      <ErrorBanner error={list.error} />
      {facets && (
        <div className="mb-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
          <Stat label="Agents" value={facets.total} />
          <Stat label="Active" value={active} sub="lifecycle ACTIVE (in view)" />
          <Stat label="Species in service" value={facets.species.length} />
          <Stat label="Departments" value={facets.departments.length} sub={`${facets.departments.filter((d: any) => !d.count).length} without agents yet`} />
        </div>
      )}
      <Card>
        <form role="search" className="grid gap-2 sm:grid-cols-2 lg:grid-cols-6" onSubmit={(e) => e.preventDefault()}>
          <label className="text-[11px] text-ink-3 lg:col-span-2">Search by name or title<input type="search" className="mt-0.5 w-full" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Malphas, Model Hunter…" /></label>
          <label className="text-[11px] text-ink-3">Department<select className="mt-0.5 w-full" value={f.department} onChange={(e) => set("department", e.target.value)}>
            <option value="">All departments</option>{facets?.departments.map((d: any) => <option key={d.key} value={d.key}>{d.name} ({d.count})</option>)}</select></label>
          <label className="text-[11px] text-ink-3">Specialization<select className="mt-0.5 w-full" value={f.specialization} onChange={(e) => set("specialization", e.target.value)}>
            <option value="">All specializations</option>{facets?.specializations.map((d: any) => <option key={d.key} value={d.key}>{d.name} ({d.count})</option>)}</select></label>
          <label className="text-[11px] text-ink-3">Race<select className="mt-0.5 w-full" value={f.species} onChange={(e) => set("species", e.target.value)}>
            <option value="">All races</option>{facets?.species.map((d: any) => <option key={d.key} value={d.key}>{d.name} ({d.count})</option>)}</select></label>
          <label className="text-[11px] text-ink-3">Status<select className="mt-0.5 w-full" value={f.status} onChange={(e) => set("status", e.target.value)}>
            <option value="">All (not archived)</option>{["ACTIVE", "PAUSED", "DISABLED", "DRAFT", "PENDING_REVIEW", "APPROVAL_REQUIRED", "READY", "FAILED", "ARCHIVED"].map((s) => <option key={s} value={s}>{s.toLowerCase().replace("_", " ")}</option>)}</select></label>
          <label className="text-[11px] text-ink-3">Sort by<select className="mt-0.5 w-full" value={f.sort} onChange={(e) => set("sort", e.target.value)}>
            <option value="name">Name</option><option value="rank">Rank</option><option value="performance">Performance (missions completed)</option><option value="activity">Recent activity</option></select></label>
          <div className="flex items-end gap-1 lg:col-span-5" role="tablist" aria-label="View">
            {(["cards", "hierarchy", "departments"] as View[]).map((v) => (
              <button key={v} type="button" role="tab" aria-selected={view === v} onClick={() => setView(v)}
                className={`rounded-md border px-3 py-1.5 text-[12.5px] pointer-coarse:min-h-10 ${view === v ? "border-violet text-violet" : "border-line text-ink-2"}`}>
                {v === "cards" ? "Register" : v === "hierarchy" ? "Chain of command" : "Departments"}</button>))}
            {(q || Object.entries(f).some(([k, v]) => k !== "sort" && v)) && <Button onClick={() => { setQ(""); setF({ department: "", specialization: "", species: "", status: "", sort: "name" }); }}>Clear filters</Button>}
          </div>
        </form>
      </Card>
      <div className="mt-4">
        {view === "cards" && (list.loading && !list.data ? <div className="text-ink-3">Loading the register…</div> :
          agents.length ? <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3" aria-label={`${agents.length} agents`}>{agents.map((a) => <AgentCard key={a.id} a={a} />)}</div>
            : <Card><Empty title="Nobody matches these filters">{canCreate ? <Link href="/personnel/create?source=PERSONNEL" className="text-violet underline">Create an agent for this</Link> : "Try fewer filters."}</Empty></Card>)}
        {view === "hierarchy" && <Hierarchy />}
        {view === "departments" && <Departments canCreate={canCreate} onShow={(k) => { set("department", k); setView("cards"); }} />}
      </div>
    </div>
  );
}

function Node({ n, depth }: { n: any; depth: number }) {
  const [open, setOpen] = useState(depth < 1);
  return (
    <li className="mt-1">
      <div className="flex min-w-0 items-center gap-2">
        {n.children.length > 0 ? <button aria-expanded={open} aria-label={`${open ? "Collapse" : "Expand"} ${n.display}`} onClick={() => setOpen(!open)} className="w-5 text-ink-3 hover:text-ink">{open ? "▾" : "▸"}</button> : <span className="w-5" />}
        <Sigil species={n.species} name={n.display} size={26} />
        <Link href={`/personnel/${n.id}`} className="min-w-0 text-[13px] text-ink hover:text-violet [overflow-wrap:anywhere]">{n.display}</Link>
        <span className="hidden text-[11px] text-ink-3 sm:inline">{n.title} · {n.rank}</span>
        {n.lifecycle !== "ACTIVE" && <StatusBadge status={lc(n.lifecycle)} />}
        {n.children.length > 0 && <span className="num text-[11px] text-ink-3">{n.children.length}</span>}
      </div>
      {open && n.children.length > 0 && <ul className="ml-3 border-l border-line pl-3">{n.children.map((c: any) => <Node key={c.id} n={c} depth={depth + 1} />)}</ul>}
    </li>
  );
}

function Hierarchy() {
  const h = useApi<any>("/api/personnel/hierarchy");
  return (
    <Card title="Chain of command" action={<span className="text-[11px] text-ink-3">{h.data?.note}</span>}>
      <ErrorBanner error={h.error} />
      <ul aria-label="Chain of command">{h.data?.roots.map((r: any) => <Node key={r.id} n={r} depth={0} />)}</ul>
      <p className="mt-3 text-[11.5px] text-ink-3">G-SUS leads operationally — and can never override the human owner, laws, governance, budgets, approvals, security rules or the kill switch. Fictional obedience is not a technical permission.</p>
    </Card>
  );
}

function Departments({ canCreate, onShow }: { canCreate: boolean; onShow: (key: string) => void }) {
  const d = useApi<any>("/api/departments");
  return (
    <div>
      <ErrorBanner error={d.error} />
      <p className="mb-3 text-[12.5px] text-ink-3">{d.data?.note}</p>
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {d.data?.departments.map((x: any) => (
          <Card key={x.key} title={`${x.name} · ${x.count}`}>
            <p className="text-[12.5px] text-ink-2">{x.description}</p>
            <div className="mt-2 text-[11.5px] text-ink-3">Lead: {x.manager ? <Link className="underline decoration-dotted" href={`/personnel/${x.manager_id}`}>{x.manager}</Link> : "none"}</div>
            {x.species_mix.length > 0 && <div className="mt-1 text-[11.5px] text-ink-3">Races here: {x.species_mix.join(", ")}</div>}
            {x.count === 0 && <div className="mt-2 text-[12px] text-ink-3">No agents yet. {canCreate && <Link className="text-violet underline" href={`/personnel/create?source=PERSONNEL&department=${x.key}`}>Create the first one</Link>}</div>}
            {x.count > 0 && <button className="mt-2 text-[12px] text-violet underline" onClick={() => onShow(x.key)}>Show members</button>}
          </Card>
        ))}
      </div>
    </div>
  );
}

export default function Page() {
  return <Suspense><Personnel /></Suspense>;
}
