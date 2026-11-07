"use client";
/** An agent's personnel file: identity, race, job, purpose, skills & tools, hierarchy, supervisor & subordinates,
 *  permissions & limits, current missions, history, results, communication style and relationships — plus the
 *  management actions. Identity edits are versioned; permissions and tool grants change only through governance. */
import Link from "next/link";
import { use, useState } from "react";
import { GovernedResult } from "@/components/governed";
import { ChipPicker, ClassLabel, LinesField, Sigil, SkillChip, SkillsEditor, Tests, fieldErrors, lc, readError } from "@/components/personnel";
import { Button, Card, Empty, ErrorBanner, PageHeader, Stat, StatusBadge } from "@/components/ui";
import { ago, api, pct } from "@/lib/api";
import { useApi, useMe, useRefreshOn } from "@/lib/hooks";

export default function Profile({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const p = useApi<any>(`/api/personnel/${id}`, [id]);
  useRefreshOn(["task"], p.reload);
  const me = useMe();
  const may = (perm: string) => !!me?.permissions?.includes(perm);
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const a = p.data;
  if (!a) return p.error ? <ErrorBanner error={p.error} /> : <div className="text-ink-3">Opening the personnel file…</div>;

  const act = async (label: string, f: () => Promise<any>, done?: (r: any) => string) => {
    setBusy(label); setErr(null); setMsg(null);
    try { const r = await f(); setMsg(done ? done(r) : `${label}: done.`); p.reload(); } catch (e) { setErr(readError(e)); } finally { setBusy(null); }
  };
  const lifecycle = (action: string) => act(action, () => api(`/api/personnel/agents/${id}/lifecycle`, { method: "POST", json: { action } }), (r) => `Now ${r.lifecycle}.`);
  const L = a.lifecycle as string;
  const perms = a.permissions;
  return (
    <div>
      <div className="mb-2 text-[12px] text-ink-3"><Link href="/personnel" className="underline decoration-dotted">Personnel</Link> / {a.persona_name}</div>
      <div className="mb-6 flex flex-wrap items-start gap-4">
        <Sigil species={a.species} name={a.persona_name} size={88} />
        <div className="min-w-0 flex-1">
          <PageHeader title={a.display} kicker={`${a.title} · ${a.rank}${a.department ? ` · ${a.department.name}` : ""}`}>
            <StatusBadge status={lc(L)} /><StatusBadge status={a.observation.state} />
            <span className="rounded border border-line px-1.5 py-0.5 font-mono text-[11px] text-ink-2" title="Permission level — set only through governance">level {a.permission_level}</span>
          </PageHeader>
          <p className="-mt-3 max-w-3xl text-[13px] text-ink-2">{a.purpose || a.description}</p>
          <p className="mt-1 text-[12px] text-ink-3">{a.observation.note}</p>
        </div>
      </div>
      <ErrorBanner error={err} />
      {msg && <div role="status" className="mb-3 rounded-md border border-good/40 bg-good/10 px-3 py-2 text-[13px] text-good">{msg}</div>}
      {may("agent.develop") && (
        <Card title="Manage" className="mb-4">
          <div className="flex flex-wrap gap-2">
            <Button variant="primary" onClick={() => setEditing(!editing)}>{editing ? "Close editor" : "Edit agent"}</Button>
            {L === "ACTIVE" && a.id !== "gsus" && <Button busy={busy === "pause"} onClick={() => lifecycle("pause")}>Pause</Button>}
            {(L === "PAUSED" || L === "DISABLED") && <Button busy={busy === "resume"} onClick={() => lifecycle("resume")}>Resume</Button>}
            {["ACTIVE", "PAUSED", "READY", "FAILED", "APPROVAL_REQUIRED"].includes(L) && a.id !== "gsus" && <Button busy={busy === "disable"} onClick={() => lifecycle("disable")}>Disable</Button>}
            {a.custom && L !== "ARCHIVED" && <Button variant="danger" busy={busy === "archive"} onClick={() => lifecycle("archive")}>Archive</Button>}
            {L === "DRAFT" && <Button busy={busy === "submit"} onClick={() => lifecycle("submit")}>Submit for review</Button>}
            {L === "DRAFT" && <Link href={`/personnel/create?draft=${a.id}&source=${a.source}`} className="inline-flex items-center rounded-md border border-line-strong px-3 py-1.5 text-[13px] text-ink-2">Continue in the Creator</Link>}
            <Button busy={busy === "test"} onClick={() => act("test", () => api(`/api/personnel/agents/${id}/test`, { method: "POST" }), (r) => `Capability checks: ${r.passed} passed, ${r.failed} failed, ${r.skipped} skipped.`)}>Run test</Button>
            {a.custom && ["READY", "FAILED"].includes(L) && <Button busy={busy === "onboard"} onClick={() => act("onboard", () => api(`/api/personnel/agents/${id}/onboarding`, { method: "POST" }), (r) => `Onboarding: ${r.summary} → ${r.lifecycle}.`)}>Run onboarding</Button>}
            {a.custom && L === "ACTIVE" && <Button busy={busy === "evaluate"} onClick={() => act("evaluate", () => api(`/api/personnel/agents/${id}/evaluate`, { method: "POST" }), (r) => `Submitted evaluation tasks ${r.tasks.map((t: number) => `#${t}`).join(", ")}.`)}>Run evaluation tasks</Button>}
          </div>
          {editing && <Editor a={a} onSaved={() => { setEditing(false); setMsg("Saved — a new version was recorded."); p.reload(); }} />}
        </Card>
      )}
      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="1 · Identity & personality">
          <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-[13px]">
            <dt className="text-ink-3">Name</dt><dd>{a.identity.persona_name}{a.identity.alt_names.length ? ` (also: ${a.identity.alt_names.join(", ")})` : ""}</dd>
            <dt className="text-ink-3">Role</dt><dd>{a.role_name}</dd>
            <dt className="text-ink-3">Traits</dt><dd className="flex flex-wrap gap-1">{a.identity.traits.length ? a.identity.traits.map((t: string) => <span key={t} className="rounded-full border border-violet/40 px-2 py-px text-[12px] text-violet">{t}</span>) : "—"}</dd>
          </dl>
          {a.identity.personality && <p className="mt-2 font-serif text-[13.5px] text-ink-2">{a.identity.personality}</p>}
          <p className="mt-2 text-[11.5px] text-ink-3">{a.identity.note}</p>
        </Card>
        <Card title="2 · Race & specialization">
          <div className="flex flex-wrap items-center gap-2 text-[13px]">
            {a.species ? <Link href={a.race.article} className="font-semibold text-ink underline decoration-dotted hover:text-violet">{a.species.name}</Link> : <span className="text-ink-3">species not set</span>}
            {a.species?.user_created && <ClassLabel kind="user_created" />}
          </div>
          {a.race.folklore_excerpt && <p className="mt-2 text-[12.5px] text-ink-2"><ClassLabel kind="folklore" /> {a.race.folklore_excerpt}</p>}
          {a.race.canon_excerpt && <p className="mt-1 text-[12.5px] text-ink-2"><ClassLabel kind="canon" /> {a.race.canon_excerpt}</p>}
          <div className="mt-2 flex flex-wrap gap-1.5">{a.specializations.map((s: any) => <span key={s.key} className="rounded border border-cyan/40 px-1.5 py-px text-[12px] text-cyan">{s.name}{s.custom ? " (custom)" : ""}</span>)}</div>
          <p className="mt-2 text-[11.5px] text-ink-3">{a.race.note}</p>
        </Card>
        <Card title="3 · Job description">
          <p className="text-[13px] text-ink-2">{a.job.description}</p>
          <Mission m={a.job.mission} />
        </Card>
        <Card title="4 · Purpose"><p className="font-serif text-[14px] text-ink">{a.purpose || "—"}</p></Card>
        <Card title="5 · Skills & tools">
          <div className="flex flex-wrap gap-1">{a.tools.skills.length ? a.tools.skills.map((s: any) => <SkillChip key={s.name} s={s} />) : <span className="text-[12.5px] text-ink-3">No skills recorded.</span>}</div>
          <div className="mt-3 text-[12px] text-ink-3">Suggested tools (not access): {a.tools.suggestions.join(", ") || "none"}</div>
          <div className="mt-1 text-[12px] text-ink-3">Granted tools: {perms.tool_grants.length ? perms.tool_grants.map((g: any) => `${g.tool} ${g.operations.join("/")}${g.enabled ? "" : " (revoked)"}`).join(", ") : "none — deny by default"}</div>
          {may("tools.grant") && <GrantForm agentId={a.id} suggestions={a.tools.suggestions} onDone={p.reload} />}
        </Card>
        <Card title="6 · Position in the hierarchy">
          <div className="text-[13px]">{a.hierarchy.department?.name ?? "No department"} · {a.hierarchy.rank}</div>
          <ol className="mt-2 space-y-1 text-[12.5px]" aria-label="Chain of command">
            {a.hierarchy.chain_of_command.length ? a.hierarchy.chain_of_command.map((c: any, i: number) => <li key={c.id}>{"↑".repeat(i + 1)} <Link className="underline decoration-dotted" href={`/personnel/${c.id}`}>{c.name}</Link> <span className="text-ink-3">{c.title}</span></li>)
              : <li className="text-ink-3">Top of the chain — answers to the human owner and governance.</li>}
          </ol>
        </Card>
        <Card title="7 · Supervisor & subordinates">
          <div className="text-[13px]">Supervisor: {a.supervisor ? <Link className="underline decoration-dotted" href={`/personnel/${a.supervisor.id}`}>{a.supervisor.name}</Link> : "—"}</div>
          <div className="mt-2 text-[12px] text-ink-3">Subordinates ({a.subordinates.length})</div>
          <ul className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-[12.5px]">{a.subordinates.map((s: any) => <li key={s.id}><Link className="underline decoration-dotted" href={`/personnel/${s.id}`}>{s.name}</Link></li>)}</ul>
        </Card>
        <Card title="8 · Permissions & limits">
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
            <Stat label="Level" value={perms.permission_level} />
            <Stat label="Actions allowed" value={perms.allowed_actions.length} />
            <Stat label="Tokens today" value={`${perms.tokens_today}/${perms.daily_token_budget}`} />
          </div>
          <details className="mt-2 text-[12px]"><summary className="cursor-pointer text-ink-2">Allowed by level / always need a human approval</summary>
            <p className="mt-1 text-ink-3">{perms.allowed_actions.join(", ") || "none"}</p><p className="mt-1 text-warning">{perms.approval_required_actions.join(", ")}</p></details>
          {perms.not_to_do.length > 0 && <ul className="mt-2 list-disc pl-5 text-[12.5px] text-ink-2">{perms.not_to_do.map((x: string) => <li key={x}>{x}</li>)}</ul>}
          <p className="mt-2 text-[11.5px] text-ink-3">{perms.note}</p>
        </Card>
        <Card title="9 · Current missions">
          {a.current_missions.length ? <ul className="space-y-1 text-[12.5px]">{a.current_missions.map((t: any) => <li key={t.id}><Link className="underline" href={`/agents?task=${t.id}`}>#{t.id} {t.type}</Link> <StatusBadge status={t.status} /></li>)}</ul>
            : <Empty title="No mission in progress" />}
          <MissionForm a={a} canRun={may("work.run")} onDone={(t) => { setMsg(`Mission submitted as task #${t}.`); p.reload(); }} />
        </Card>
        <Card title="10 · History">
          <div className="text-[12px] text-ink-3">Recent tasks</div>
          <ul className="mt-1 max-h-48 space-y-0.5 overflow-auto text-[12px]">{a.history.tasks.map((t: any) => <li key={t.id}><Link className="underline decoration-dotted" href={`/agents?task=${t.id}`}>#{t.id}</Link> {t.type} <StatusBadge status={t.status} /> <span className="text-ink-3">{ago(t.created_at)}</span></li>)}
            {!a.history.tasks.length && <li className="text-ink-3">No tasks yet.</li>}</ul>
          <div className="mt-3 text-[12px] text-ink-3">Profile versions (nothing is overwritten)</div>
          <ul className="mt-1 max-h-40 space-y-0.5 overflow-auto text-[12px]">{a.history.versions.map((v: any) => <li key={v.version}>v{v.version} · {v.note} · <span className="text-ink-3">{v.changed_by} · {ago(v.changed_at)}</span></li>)}
            {!a.history.versions.length && <li className="text-ink-3">Seeded identity (v1); edits will appear here.</li>}</ul>
        </Card>
        <Card title="11 · Results & evaluations">
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            <Stat label="Succeeded" value={a.results.succeeded} /><Stat label="Failed" value={a.results.failed} />
            <Stat label="Blocked" value={a.results.blocked} /><Stat label="Success rate" value={a.results.success_rate === null ? "—" : pct(a.results.success_rate)} />
          </div>
          <div className="mt-2 text-[12px] text-ink-3">{a.results.model_calls} model calls · ${a.results.cost_total_usd?.toFixed?.(4) ?? a.results.cost_total_usd} · {a.results.note}</div>
          {a.achievements.length > 0 && <div className="mt-2 text-[12.5px] text-gold">★ {a.achievements.join(" · ")}</div>}
          <Tests t={a.results.onboarding?.tests} />
        </Card>
        <Card title="12 · Communication style">
          <div className="flex flex-wrap gap-1.5 text-[12.5px]">{a.communication.styles.map((s: string) => <span key={s} className="rounded border border-line px-1.5 py-px">{s}</span>)}{!a.communication.styles.length && <span className="text-ink-3">—</span>}</div>
          <div className="mt-2 text-[12px] text-ink-3">Languages: {a.communication.languages.join(", ") || "—"}</div>
        </Card>
        <Card title="13 · Relationships">
          {a.relationships.length ? <ul className="space-y-1 text-[12.5px]">{a.relationships.map((r: any) => <li key={r.id}><span className="font-mono text-[11px] text-ink-3">{r.type}</span> <Link className="underline decoration-dotted" href={`/personnel/${r.with.id}`}>{r.with.name}</Link> — <span className="text-ink-2">{r.description}</span></li>)}</ul>
            : <Empty title="No relationships recorded" />}
          <p className="mt-2 text-[11.5px] text-ink-3">Friendships and rivalries are character colour; they never grant or deny anything.</p>
        </Card>
        <Card title="Task trace">
          <p className="text-[13px] text-ink-2">{a.trace.tasks_traced} traced task(s). {a.trace.observation.state === "observed" ? <span className="text-cyan">“{a.trace.observation.note}”</span> : a.trace.observation.note}</p>
          <Link className="mt-1 inline-block text-[12px] text-violet underline" href={`/agents?agent=${a.id}`}>Open in the Agent Registry</Link>
        </Card>
      </div>
    </div>
  );
}

function Mission({ m }: { m: any }) {
  const rows: [string, string[] | string][] = [["Primary tasks", m.primary], ["Secondary tasks", m.secondary], ["Goals", m.goals], ["Expected outcomes", m.outcomes], ["Long-term", m.long_term]];
  return <dl className="mt-2 space-y-1 text-[12.5px]">{rows.filter(([, v]) => v && v.length).map(([k, v]) => <div key={k}><dt className="text-ink-3">{k}</dt><dd className="text-ink-2">{Array.isArray(v) ? v.join(" · ") : v}</dd></div>)}</dl>;
}

function MissionForm({ a, canRun, onDone }: { a: any; canRun: boolean; onDone: (task: number) => void }) {
  const [obj, setObj] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  if (!a.custom) return <p className="mt-3 text-[12px] text-ink-3">{a.persona_name} takes structured tasks — give the mission to <Link className="text-violet underline" href="/chamber">G-SUS</Link>, who plans and delegates it.</p>;
  if (a.lifecycle !== "ACTIVE") return <p className="mt-3 text-[12px] text-ink-3">Missions can be assigned once {a.persona_name} is ACTIVE.</p>;
  if (!canRun) return null;
  const send = async () => {
    setBusy(true); setErr(null);
    try { const r = await api(`/api/personnel/agents/${a.id}/missions`, { method: "POST", json: { objective: obj } }); setObj(""); onDone(r.task_id); }
    catch (e) { setErr(readError(e)); } finally { setBusy(false); }
  };
  return (
    <div className="mt-3">
      <label className="block text-[11px] text-ink-3">Assign a mission<textarea rows={2} className="mt-0.5 w-full" value={obj} onChange={(e) => setObj(e.target.value)} placeholder="What should this agent do?" /></label>
      <ErrorBanner error={err} />
      <Button busy={busy} disabled={obj.trim().length < 3} onClick={send}>Assign mission</Button>
    </div>
  );
}

function GrantForm({ agentId, suggestions, onDone }: { agentId: string; suggestions: string[]; onDone: () => void }) {
  const meta = useApi<any>("/api/personnel/meta");
  const [tool, setTool] = useState(suggestions[0] ?? "");
  const [reason, setReason] = useState("");
  const [res, setRes] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);
  const t = meta.data?.tools.find((x: any) => x.name === tool);
  const send = async () => {
    setErr(null);
    try { setRes(await api("/api/tools/grants", { method: "POST", json: { subject_kind: "agent", subject_id: agentId, tool, operations: [t.operation], reason } })); onDone(); }
    catch (e) { setErr((e as Error).message); }
  };
  return (
    <details className="mt-3 text-[12.5px]"><summary className="cursor-pointer text-ink-2">Modify tool grants (through governance)</summary>
      <div className="mt-2 grid gap-2 sm:grid-cols-2">
        <label className="text-[11px] text-ink-3">Tool<select className="mt-0.5 w-full" value={tool} onChange={(e) => setTool(e.target.value)}>
          <option value="">Choose…</option>{meta.data?.tools.map((x: any) => <option key={x.name} value={x.name}>{x.name} · {x.operation}</option>)}</select></label>
        <label className="text-[11px] text-ink-3">Reason (audited)<input className="mt-0.5 w-full" value={reason} onChange={(e) => setReason(e.target.value)} /></label>
      </div>
      <div className="mt-2"><Button disabled={!t || reason.length < 3} onClick={send}>Request grant</Button></div>
      <ErrorBanner error={err} />
      <GovernedResult res={res} onApplied={onDone} />
      <p className="mt-1 text-[11px] text-ink-3">Grants are RESTRICTED: filed as an approval that someone else decides. Revoking is done in Governance.</p>
    </details>
  );
}

function Editor({ a, onSaved }: { a: any; onSaved: () => void }) {
  const meta = useApi<any>("/api/personnel/meta");
  const best = useApi<any>("/api/bestiary");
  const staff = useApi<any>("/api/personnel");
  const init = {
    persona_name: a.identity.persona_name, title: a.title, species_key: a.species?.key ?? "", specializations: a.specializations.map((s: any) => s.key),
    department_key: a.department?.key ?? "", rank: a.rank, supervisor_id: a.supervisor?.id ?? "", traits: a.identity.traits,
    personality: a.identity.personality ?? "", purpose: a.purpose ?? "", mission: a.job.mission ?? {}, communication_style: a.communication.styles,
    languages: a.communication.languages, skills: a.tools.skills,
  };
  const [s, setS] = useState<any>(init);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [fe, setFe] = useState<Record<string, string>>({});
  const set = (k: string, v: any) => setS((x: any) => ({ ...x, [k]: v }));
  const m = meta.data;
  const save = async () => {
    const changes = Object.fromEntries(Object.entries(s).filter(([k, v]) => JSON.stringify(v) !== JSON.stringify((init as any)[k])));
    if (changes.rank && !m.ranks.includes(changes.rank)) { changes.custom_rank = changes.rank; changes.rank = "Custom"; }
    if (!Object.keys(changes).length) { setErr("Nothing changed."); return; }
    setBusy(true); setErr(null); setFe({});
    try { await api(`/api/personnel/agents/${a.id}`, { method: "PATCH", json: { changes, note } }); onSaved(); }
    catch (e) { setErr(readError(e)); setFe(fieldErrors(e)); } finally { setBusy(false); }
  };
  if (!m) return <div className="mt-3 text-ink-3">Loading…</div>;
  return (
    <div className="mt-4 space-y-3 border-t border-line pt-4">
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        <label className="text-[11px] text-ink-3">Name<input className="mt-0.5 w-full" value={s.persona_name} onChange={(e) => set("persona_name", e.target.value)} aria-invalid={!!fe.persona_name} />{fe.persona_name && <span className="text-warning">{fe.persona_name}</span>}</label>
        <label className="text-[11px] text-ink-3">Title / role<input className="mt-0.5 w-full" value={s.title} onChange={(e) => set("title", e.target.value)} /></label>
        <label className="text-[11px] text-ink-3">Species<select className="mt-0.5 w-full" value={s.species_key} onChange={(e) => set("species_key", e.target.value)}>
          {best.data?.species.filter((x: any) => x.kind === "being").map((x: any) => <option key={x.key} value={x.key}>{x.name}</option>)}</select></label>
        <label className="text-[11px] text-ink-3">Department<select className="mt-0.5 w-full" value={s.department_key} onChange={(e) => set("department_key", e.target.value)}>
          {m.departments.map((d: any) => <option key={d.key} value={d.key}>{d.name}</option>)}</select></label>
        <label className="text-[11px] text-ink-3">Rank<select className="mt-0.5 w-full" value={m.ranks.includes(s.rank) ? s.rank : "Custom"} onChange={(e) => set("rank", e.target.value)}>
          {m.ranks.map((r: string) => <option key={r}>{r}</option>)}</select></label>
        {a.id !== "gsus" && <label className="text-[11px] text-ink-3">Supervisor<select className="mt-0.5 w-full" value={s.supervisor_id} onChange={(e) => set("supervisor_id", e.target.value)} aria-invalid={!!fe.supervisor_id}>
          {staff.data?.agents.filter((x: any) => x.id !== a.id).map((x: any) => <option key={x.id} value={x.id}>{x.persona_name} — {x.title}</option>)}</select>{fe.supervisor_id && <span className="text-warning">{fe.supervisor_id}</span>}</label>}
      </div>
      <ChipPicker label="Specializations" options={m.specializations.map((x: any) => x.key)} value={s.specializations} onChange={(v) => set("specializations", v)} max={6} />
      <ChipPicker label="Personality traits" options={m.traits} value={s.traits} onChange={(v) => set("traits", v)} max={8} />
      <label className="block text-[11px] text-ink-3">Personality (free text)<textarea rows={2} className="mt-0.5 w-full" value={s.personality} onChange={(e) => set("personality", e.target.value)} /></label>
      <label className="block text-[11px] text-ink-3">Purpose<textarea rows={2} className="mt-0.5 w-full" value={s.purpose} onChange={(e) => set("purpose", e.target.value)} /></label>
      <div className="grid gap-3 sm:grid-cols-2">
        <LinesField label="Primary tasks" value={s.mission.primary ?? []} onChange={(v) => set("mission", { ...s.mission, primary: v })} />
        <LinesField label="Must not do" value={s.mission.not_to_do ?? []} onChange={(v) => set("mission", { ...s.mission, not_to_do: v })} />
      </div>
      <ChipPicker label="Communication style" options={m.communication_styles} value={s.communication_style} onChange={(v) => set("communication_style", v)} max={4} />
      <ChipPicker label="Languages" options={m.languages} value={s.languages} onChange={(v) => set("languages", v)} max={6} />
      <SkillsEditor value={s.skills} onChange={(v) => set("skills", v)} levels={m.skill_levels} />
      <label className="block text-[11px] text-ink-3">Change note (kept in the history)<input className="mt-0.5 w-full" value={note} onChange={(e) => setNote(e.target.value)} placeholder="e.g. promoted after the Q3 review" /></label>
      <ErrorBanner error={err} />
      <div className="flex gap-2"><Button variant="primary" busy={busy} onClick={save}>Save changes</Button></div>
      <p className="text-[11px] text-ink-3">The permission level and tool grants are not edited here — they change only through governance (approvals and the Tool Gateway).</p>
    </div>
  );
}
