"use client";
/** CUSTOM AGENT CREATOR — a ten-step recruitment flow with a live preview. Every entry point (Personnel, The Bestiary,
 *  G-SUS chat) lands here or calls the same endpoint, so there is one creation pipeline. AI buttons call the creator's
 *  design/generate endpoints (budgeted, traced, rules fallback labelled as such); nothing is created until "Create". */
import Link from "next/link";
import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Sparkles, Wand2 } from "lucide-react";
import { ChipPicker, ClassLabel, LinesField, Sigil, SkillChip, SkillsEditor, Tests, readError } from "@/components/personnel";
import { Button, Card, ErrorBanner, PageHeader, StatusBadge } from "@/components/ui";
import { api } from "@/lib/api";
import { useApi, useMe } from "@/lib/hooks";

const STEPS = ["Identity", "Species", "Specialization", "Personality", "Mission", "Competencies", "Tools", "Permissions", "Review", "Create Agent"];
const STEP_FIELDS: string[][] = [["persona_name", "title"], ["species_key", "custom_species"], ["specializations", "department_key", "custom_rank", "supervisor_id"],
  ["traits"], ["purpose"], ["skills"], ["tool_suggestions"], ["permission_level"], [], []];
const LOCAL_KEY = "rocky.creator.v1";
const EMPTY = { persona_name: "", alt_names: [] as string[], title: "", description: "", species_key: "", subspecies: "", custom_species: null as any,
  specializations: [] as string[], department_key: "", department_suggestion: null as any, rank: "Specialist", custom_rank: "", traits: [] as string[],
  personality: "", purpose: "", mission: { primary: [], secondary: [], long_term: "", goals: [], outcomes: [], not_to_do: [] } as any,
  skills: [] as any[], tool_suggestions: [] as string[], communication_style: [] as string[], languages: ["English"], success_criteria: [] as string[],
  supervisor_id: "gsus", permission_level: 1 };
type Spec = typeof EMPTY;
const LEVELS = [
  { n: 0, label: "0 · Research", d: "Read and collect only." },
  { n: 1, label: "1 · Analysis (default)", d: "Analyse and report. What every new agent starts with." },
  { n: 2, label: "2 · Drafting", d: "Draft content, concepts and inquiries — never sends or publishes. Needs approval." },
  { n: 3, label: "3 · Reversible internal operations", d: "Create drafts and internal records. Needs approval." },
];

function Creator() {
  const params = useSearchParams();
  const me = useMe();
  const canAI = !!me?.permissions?.includes("work.run");
  const canCreate = !!me?.permissions?.includes("agent.develop");
  const source = (params.get("source") || "PERSONNEL").toUpperCase();
  const meta = useApi<any>("/api/personnel/meta");
  const [spec, setSpec] = useState<Spec>(EMPTY);
  const [step, setStep] = useState(0);
  const [draftId, setDraftId] = useState<string | null>(params.get("draft"));
  const [loaded, setLoaded] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const set = useCallback((k: keyof Spec, v: any) => setSpec((s) => ({ ...s, [k]: v })), []);

  // ---- where the creator was opened from: G-SUS hand-off, a draft, the Bestiary, or a local autosave
  useEffect(() => {
    (async () => {
      let next: Spec = { ...EMPTY };
      try {
        if (params.get("from") === "gsus") {
          const h = JSON.parse(sessionStorage.getItem("rocky.creator.handoff") || "null");
          if (h?.spec) { next = { ...EMPTY, ...h.spec }; setNotice("Loaded G-SUS's proposal — edit anything, then create."); }
        } else if (params.get("draft")) {
          const prof = await api<any>(`/api/personnel/${params.get("draft")}`);
          const d = prof.results?.onboarding?.draft_spec;
          if (d) { next = { ...EMPTY, ...d }; setNotice(`Continuing draft ${prof.persona_name}.`); }
        } else {
          const saved = JSON.parse(localStorage.getItem(LOCAL_KEY) || "null");
          if (saved?.spec && !params.get("species")) { next = { ...EMPTY, ...saved.spec }; setStep(saved.step ?? 0); setNotice("Restored your unfinished agent from this browser."); }
        }
      } catch { /* storage unavailable or draft missing: start fresh */ }
      if (params.get("species")) next.species_key = params.get("species")!;
      if (params.get("department")) next.department_key = params.get("department")!;
      setSpec(next);
      setLoaded(true);
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  useEffect(() => { if (loaded) try { localStorage.setItem(LOCAL_KEY, JSON.stringify({ spec, step })); } catch { /* per-viewer convenience only */ } }, [spec, step, loaded]);

  // ---- live preview (validation + duplicates) from the real service, debounced
  const [pv, setPv] = useState<any>(null);
  const [pvErr, setPvErr] = useState<string | null>(null);
  useEffect(() => {
    if (!loaded || !canAI) return;
    const t = setTimeout(async () => {
      try { setPv(await api("/api/personnel/preview", { method: "POST", json: { spec, exclude_id: draftId } })); setPvErr(null); }
      catch (e) { setPvErr(readError(e)); }
    }, 400);
    return () => clearTimeout(t);
  }, [spec, loaded, canAI, draftId]);
  // a step's problems are shown once the person has left that step (or reaches Review) — not before they start typing
  const [left, setLeft] = useState<Set<number>>(new Set());
  const goto = (i: number) => { setLeft((prev) => new Set(prev).add(step)); setStep(i); };
  const errs: Record<string, string> = Object.fromEntries((pv?.validation?.errors ?? [])
    .filter((e: any) => step >= 8 || left.has(STEP_FIELDS.findIndex((fs) => fs.includes(e.field))))
    .map((e: any) => [e.field, e.message]));

  // ---- AI
  const [idea, setIdea] = useState("");
  const [aiBusy, setAiBusy] = useState<string | null>(null);
  const [aiNote, setAiNote] = useState<string | null>(null);
  const [aiErr, setAiErr] = useState<string | null>(null);
  const [design, setDesign] = useState<any>(null);
  const [recs, setRecs] = useState<any[]>([]);
  const gen = async (field: string) => {
    setAiBusy(field); setAiErr(null); setAiNote(null);
    try {
      const r = await api<any>("/api/personnel/generate", { method: "POST", json: { field, spec, idea } });
      if (field === "name") set("persona_name", r.value);
      if (field === "species") { setRecs(r.recommendations ?? []); if (r.value) set("species_key", r.value); }
      if (field === "personality") setSpec((s) => ({ ...s, traits: r.value.traits?.length ? r.value.traits : s.traits, personality: r.value.summary || s.personality,
        communication_style: r.value.communication_style?.length ? r.value.communication_style : s.communication_style }));
      if (field === "specialization") set("specializations", r.value);
      if (field === "mission") setSpec((s) => ({ ...s, mission: { ...s.mission, ...r.value } }));
      if (field === "skills") set("skills", r.value);
      setAiNote(`${r.method === "model" ? `AI (${r.model})` : "Rules (no model)"}${r.notes?.length ? " — " + r.notes.join(" ") : ""}`);
    } catch (e) { setAiErr(readError(e)); } finally { setAiBusy(null); }
  };
  const designAll = async (alternatives: number) => {
    setAiBusy("design"); setAiErr(null); setAiNote(null);
    const prefill: Record<string, any> = {};
    if (params.get("species") && spec.species_key) prefill.species_key = spec.species_key;   // a Bestiary choice stays fixed
    try {
      const r = await api<any>("/api/personnel/design", { method: "POST", json: { idea, prefill, alternatives, source } });
      setDesign(r); setRecs(r.species_recommendations ?? []);
      setAiNote(`${r.method === "model" ? `Designed by AI (${r.model})` : "Assembled by deterministic rules (no model available)"}${r.notes?.length ? " — " + r.notes.join(" ") : ""}`);
    } catch (e) { setAiErr(readError(e)); } finally { setAiBusy(null); }
  };
  const AI = ({ field, label }: { field: string; label: string }) => canAI
    ? <Button busy={aiBusy === field} onClick={() => gen(field)} title="Uses the AI gateway when a model is available; otherwise deterministic rules"><Wand2 size={13} /> {label}</Button> : null;

  // ---- save / create
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [dupChoice, setDupChoice] = useState<string>("");
  const [extendId, setExtendId] = useState<string>("");
  const [confirmed, setConfirmed] = useState(false);
  const [result, setResult] = useState<any>(null);
  const saveDraft = async () => {
    setBusy("draft"); setErr(null);
    try { const r = await api<any>("/api/personnel/drafts", { method: "POST", json: { spec, source, draft_id: draftId } }); setDraftId(r.agent.id); setNotice(`Draft saved as ${r.agent.id} (DRAFT — it cannot run).`); }
    catch (e) { setErr(readError(e)); } finally { setBusy(null); }
  };
  const create = async () => {
    setBusy("create"); setErr(null);
    try {
      const r = await api<any>("/api/personnel/agents", { method: "POST", json: { spec, source, draft_id: draftId, confirmed, duplicate_choice: dupChoice || null,
        extend_id: dupChoice === "extend" ? extendId || null : null, gsus_run_id: params.get("run") ? Number(params.get("run")) : null } });
      setResult(r);
      try { localStorage.removeItem(LOCAL_KEY); sessionStorage.removeItem("rocky.creator.handoff"); } catch { /* fine */ }
    } catch (e) { setErr(readError(e)); if (String((e as any)?.status) === "409") setStep(8); } finally { setBusy(null); }
  };
  const strongDup = (pv?.duplicates ?? []).some((d: any) => d.score >= 0.35 || d.same_name);

  if (!loaded || !meta.data) return <div className="text-ink-3">Preparing the summoning circle…</div>;
  const m = meta.data;
  return (
    <div>
      <div className="mb-2 text-[12px] text-ink-3"><Link href="/personnel" className="underline decoration-dotted">Personnel</Link> / Custom Agent Creator</div>
      <PageHeader title="Custom Agent Creator" kicker={`Summon a new colleague · entry: ${source.toLowerCase().replace("_", " ")}`}>
        {canCreate && <Button busy={busy === "draft"} onClick={saveDraft} disabled={!spec.persona_name}>Save draft</Button>}
        <Button onClick={() => { setSpec({ ...EMPTY }); setStep(0); setDesign(null); setResult(null); setDraftId(null); try { localStorage.removeItem(LOCAL_KEY); } catch { /* fine */ } }}>Start over</Button>
      </PageHeader>
      {notice && <div role="status" className="mb-3 rounded-md border border-line px-3 py-2 text-[12.5px] text-ink-2">{notice}</div>}
      {!canCreate && me && <div role="status" className="mb-3 rounded-md border border-warning/40 bg-warning/10 px-3 py-2 text-[12.5px] text-warning">You can design and preview, but creating agents needs the <code>agent.develop</code> permission.</div>}
      {!canAI && me && <div role="status" className="mb-3 rounded-md border border-warning/40 bg-warning/10 px-3 py-2 text-[12.5px] text-warning">AI help and the live preview need the <code>work.run</code> permission.</div>}

      <nav aria-label="Creator steps" className="mb-4 overflow-x-auto">
        <ol className="flex min-w-max gap-1">{STEPS.map((s, i) => {
          const bad = STEP_FIELDS[i].some((f) => errs[f]);
          return <li key={s}><button onClick={() => goto(i)} aria-current={step === i ? "step" : undefined}
            className={`rounded-md border px-2.5 py-1.5 text-[12px] pointer-coarse:min-h-10 ${step === i ? "border-violet bg-violet/15 text-violet" : "border-line text-ink-2 hover:border-line-strong"}`}>
            <span className="num mr-1 text-ink-3">{i + 1}</span>{s}{bad ? <span className="ml-1 text-warning" aria-label="has problems">•</span> : null}</button></li>;
        })}</ol>
      </nav>

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_340px]">
        <Card title={`${step + 1} · ${STEPS[step]}`}>
          <h2 className="sr-only">{STEPS[step]}</h2>
          {aiNote && <div role="status" className="mb-3 text-[12px] text-cyan">{aiNote}</div>}
          <ErrorBanner error={aiErr} />
          {step === 0 && (
            <div className="space-y-4">
              {canAI && (
                <div className="rounded-lg border border-violet/40 bg-violet/5 p-3">
                  <div className="mb-1 flex items-center gap-1.5 font-mono text-[11px] uppercase tracking-[0.16em] text-violet"><Sparkles size={13} /> Let AI design my agent</div>
                  <label className="block text-[11px] text-ink-3">Describe the idea in your own words
                    <textarea rows={3} className="mt-0.5 w-full" value={idea} onChange={(e) => setIdea(e.target.value)}
                      placeholder="Jag vill ha någon som kan sköta all research kring nya AI-modeller och hitta de bästa kostnadsfria alternativen." /></label>
                  <div className="mt-2 flex flex-wrap gap-2">
                    <Button variant="primary" busy={aiBusy === "design"} disabled={idea.trim().length < 5} onClick={() => designAll(1)}>Design entire agent</Button>
                    <Button busy={aiBusy === "design"} disabled={idea.trim().length < 5} onClick={() => designAll(3)}>Compare 3 alternatives</Button>
                  </div>
                  {design && <Proposals d={design} onUse={(p) => { setSpec({ ...EMPTY, ...p }); setNotice(`Using the proposal for ${p.persona_name}. Every part stays editable.`); }} />}
                </div>
              )}
              <div className="grid gap-3 sm:grid-cols-2">
                <label className="text-[11px] text-ink-3">Name<input className="mt-0.5 w-full" value={spec.persona_name} onChange={(e) => set("persona_name", e.target.value)} aria-invalid={!!errs.persona_name} />
                  {errs.persona_name && <span className="text-warning">{errs.persona_name}</span>}</label>
                <label className="text-[11px] text-ink-3">Title or alias<input className="mt-0.5 w-full" value={spec.title} onChange={(e) => set("title", e.target.value)} placeholder="e.g. Emerging Technology Researcher" /></label>
                <label className="text-[11px] text-ink-3 sm:col-span-2">Alternative names (comma-separated)<input className="mt-0.5 w-full" value={spec.alt_names.join(", ")} onChange={(e) => set("alt_names", e.target.value.split(",").map((x) => x.trim()).filter(Boolean))} /></label>
              </div>
              <AI field="name" label="Generate name" />
            </div>
          )}
          {step === 1 && <SpeciesStep spec={spec} set={set} errs={errs} recs={recs} ai={<AI field="species" label="Suggest species" />} />}
          {step === 2 && (
            <div className="space-y-4">
              <ChipPicker label="Specializations (combine several)" options={m.specializations.map((s: any) => s.key)} value={spec.specializations} onChange={(v) => set("specializations", v)} max={6} />
              {errs.specializations && <div className="text-[12px] text-warning">{errs.specializations}</div>}
              <CustomSpec onAdd={(n) => set("specializations", [...spec.specializations, n])} />
              <AI field="specialization" label="Generate specialization" />
              <div className="grid gap-3 sm:grid-cols-2">
                <label className="text-[11px] text-ink-3">Department<select className="mt-0.5 w-full" value={spec.department_key} onChange={(e) => set("department_key", e.target.value)} aria-invalid={!!errs.department_key}>
                  <option value="">— choose, or suggest a new one below —</option>{m.departments.map((d: any) => <option key={d.key} value={d.key}>{d.name}</option>)}</select>
                  {errs.department_key && <span className="text-warning">{errs.department_key}</span>}</label>
                <Supervisor value={spec.supervisor_id} onChange={(v) => set("supervisor_id", v)} error={errs.supervisor_id} />
                <label className="text-[11px] text-ink-3">Rank / position<select className="mt-0.5 w-full" value={spec.rank} onChange={(e) => set("rank", e.target.value)}>{m.ranks.map((r: string) => <option key={r}>{r}</option>)}</select></label>
                {spec.rank === "Custom" && <label className="text-[11px] text-ink-3">Custom rank<input className="mt-0.5 w-full" value={spec.custom_rank} onChange={(e) => set("custom_rank", e.target.value)} aria-invalid={!!errs.custom_rank} /></label>}
              </div>
              <p className="text-[11.5px] text-ink-3">Rank never grants technical permissions.</p>
              <details className="text-[12.5px]"><summary className="cursor-pointer text-ink-2">Suggest a new department (only if there is a real need)</summary>
                <div className="mt-2 grid gap-2 sm:grid-cols-2">
                  <input aria-label="New department name" placeholder="Department name" value={spec.department_suggestion?.name ?? ""} onChange={(e) => set("department_suggestion", e.target.value ? { ...(spec.department_suggestion ?? {}), name: e.target.value } : null)} />
                  <input aria-label="Why it is needed" placeholder="Why is it needed?" value={spec.department_suggestion?.reason ?? ""} onChange={(e) => set("department_suggestion", { ...(spec.department_suggestion ?? { name: "" }), reason: e.target.value })} />
                </div><p className="mt-1 text-[11px] text-ink-3">A suggestion is recorded; an administrator creates the department.</p></details>
            </div>
          )}
          {step === 3 && (
            <div className="space-y-4">
              <ChipPicker label="Personality traits" options={m.traits} value={spec.traits} onChange={(v) => set("traits", v)} max={8} />
              <label className="block text-[11px] text-ink-3">…or describe the personality in your own words
                <textarea rows={3} className="mt-0.5 w-full" value={spec.personality} onChange={(e) => set("personality", e.target.value)}
                  placeholder="En smart, busig och lite arrogant demon som älskar att hitta genvägar men alltid levererar när G-SUS ger en order." /></label>
              <AI field="personality" label="Generate personality" />
              <ChipPicker label="Communication style" options={m.communication_styles} value={spec.communication_style} onChange={(v) => set("communication_style", v)} max={4} />
              <ChipPicker label="Languages" options={m.languages} value={spec.languages} onChange={(v) => set("languages", v)} max={6} />
              <p className="text-[11.5px] text-ink-3">Personality shapes expression and priorities — never security, permissions or tool access.</p>
            </div>
          )}
          {step === 4 && (
            <div className="space-y-3">
              <label className="block text-[11px] text-ink-3">Main purpose<textarea rows={2} className="mt-0.5 w-full" value={spec.purpose} onChange={(e) => set("purpose", e.target.value)} aria-invalid={!!errs.purpose} />
                {errs.purpose && <span className="text-warning">{errs.purpose}</span>}</label>
              <div className="grid gap-3 sm:grid-cols-2">
                <LinesField label="Primary tasks" value={spec.mission.primary ?? []} onChange={(v) => set("mission", { ...spec.mission, primary: v })} />
                <LinesField label="Secondary tasks" value={spec.mission.secondary ?? []} onChange={(v) => set("mission", { ...spec.mission, secondary: v })} />
                <LinesField label="Goals" value={spec.mission.goals ?? []} onChange={(v) => set("mission", { ...spec.mission, goals: v })} />
                <LinesField label="Expected results" value={spec.mission.outcomes ?? []} onChange={(v) => set("mission", { ...spec.mission, outcomes: v })} />
              </div>
              <label className="block text-[11px] text-ink-3">Long-term responsibility<input className="mt-0.5 w-full" value={spec.mission.long_term ?? ""} onChange={(e) => set("mission", { ...spec.mission, long_term: e.target.value })} /></label>
              <LinesField label="What the agent must NOT do" value={spec.mission.not_to_do ?? []} onChange={(v) => set("mission", { ...spec.mission, not_to_do: v })} />
              <LinesField label="Measurable success criteria" value={spec.success_criteria} onChange={(v) => set("success_criteria", v)} rows={2} />
              <AI field="mission" label="Generate mission" />
              <p className="text-[11.5px] text-ink-3">The governance limits (no self-granted permissions, no acting outside delegated scope, no overriding the owner or the kill switch) are always added.</p>
            </div>
          )}
          {step === 5 && <div className="space-y-3"><SkillsEditor value={spec.skills} onChange={(v) => set("skills", v)} levels={m.skill_levels} /><AI field="skills" label="Suggest skills" />
            <p className="text-[11.5px] text-ink-3">Kept apart, always: AI-generated competence profile · onboarding test · verified function · measured performance over time.</p></div>}
          {step === 6 && (
            <div>
              <p className="mb-2 text-[12.5px] text-ink-2">Only tools that exist in the Tool Gateway are listed. Choosing one is a <strong>suggestion</strong>: access is granted afterwards through governance (deny by default).</p>
              <ul className="grid gap-2 sm:grid-cols-2">{m.tools.map((t: any) => (
                <li key={t.name}><label className="flex items-start gap-2 rounded-md border border-line p-2 text-[12.5px]">
                  <input type="checkbox" className="mt-0.5" checked={spec.tool_suggestions.includes(t.name)} onChange={(e) => set("tool_suggestions", e.target.checked ? [...spec.tool_suggestions, t.name] : spec.tool_suggestions.filter((x) => x !== t.name))} />
                  <span><span className="font-mono text-ink">{t.name}</span> <span className="font-mono text-[10.5px] text-ink-3">{t.operation}</span><br /><span className="text-ink-3">{t.description}</span></span></label></li>))}</ul>
            </div>
          )}
          {step === 7 && (
            <fieldset>
              <legend className="mb-2 text-[12.5px] text-ink-2">Requested permission level</legend>
              <div className="space-y-2">{LEVELS.map((l) => (
                <label key={l.n} className="flex items-start gap-2 rounded-md border border-line p-2 text-[12.5px]">
                  <input type="radio" name="level" className="mt-0.5" checked={spec.permission_level === l.n} onChange={() => set("permission_level", l.n)} />
                  <span><span className="text-ink">{l.label}</span><br /><span className="text-ink-3">{l.d}</span></span></label>))}</div>
              <ul className="mt-3 list-disc space-y-1 pl-5 text-[12px] text-ink-3">{(pv?.governance?.rules ?? []).map((r: string) => <li key={r}>{r}</li>)}
                <li>LEVEL 4–5 cannot be requested: those actions always need a per-action human approval.</li></ul>
            </fieldset>
          )}
          {step === 8 && (
            <div className="space-y-3 text-[13px]">
              {!pv ? <div className="text-ink-3">Waiting for the preview…</div> : <>
                <div>{pv.validation.ok ? <StatusBadge status="ok" /> : <StatusBadge status="blocked" />} <span className="ml-1">{pv.validation.ok ? "The profile is valid." : `${pv.validation.errors.length} problem(s) to fix:`}</span></div>
                {pv.validation.errors.length > 0 && <ul className="list-disc pl-5 text-warning">{pv.validation.errors.map((e: any) => <li key={e.field + e.message}><button className="underline" onClick={() => goto(Math.max(0, STEP_FIELDS.findIndex((fs) => fs.includes(e.field))))}>{e.field}</button>: {e.message}</li>)}</ul>}
                {pv.validation.warnings.length > 0 && <ul className="list-disc pl-5 text-ink-3">{pv.validation.warnings.map((w: string) => <li key={w}>{w}</li>)}</ul>}
                {pv.duplicates?.length > 0 && (
                  <fieldset className="rounded-md border border-warning/40 p-3">
                    <legend className="px-1 text-warning">Existing agents cover similar ground</legend>
                    <ul className="mb-2 space-y-1">{pv.duplicates.map((d: any) => <li key={d.agent.id}><Link className="underline" href={`/personnel/${d.agent.id}`}>{d.agent.display}</Link> <span className="num text-ink-3">similarity {d.score.toFixed(2)} → {d.recommendation.replace("_", " ")}{d.same_name ? " · same name" : ""}</span><div className="text-[11.5px] text-ink-3">shared: {d.shared.join(", ")}</div></li>)}</ul>
                    <div className="flex flex-wrap gap-3">{[["use_existing", "Use the existing agent"], ["extend", "Extend its skills"], ["complement", "Create a complementary specialist"], ["new", "Create a completely new agent"]].map(([k, l]) => (
                      <label key={k} className="inline-flex items-center gap-1"><input type="radio" name="dup" checked={dupChoice === k} onChange={() => { setDupChoice(k); if (k === "extend") setExtendId(pv.duplicates[0].agent.id); }} />{l}</label>))}</div>
                    {dupChoice === "extend" && <label className="mt-2 block text-[11px] text-ink-3">Extend<select className="mt-0.5 w-full" value={extendId} onChange={(e) => setExtendId(e.target.value)}>{pv.duplicates.map((d: any) => <option key={d.agent.id} value={d.agent.id}>{d.agent.display}</option>)}</select></label>}
                    <p className="mt-2 text-[11px] text-ink-3">Several agents with similar skills are fine when there is a real need for parallel work, independent review or redundancy.</p>
                  </fieldset>)}
                <details><summary className="cursor-pointer text-ink-2">Working instructions the agent will receive</summary><pre className="mt-2 whitespace-pre-wrap rounded-md bg-bg p-2 text-[11.5px] text-ink-2">{pv.instructions_preview}</pre></details>
              </>}
            </div>
          )}
          {step === 9 && (
            <div className="space-y-3 text-[13px]">
              {!result ? <>
                <label className="flex items-start gap-2"><input type="checkbox" className="mt-0.5" checked={confirmed} onChange={(e) => setConfirmed(e.target.checked)} />
                  <span>I have reviewed the profile. Create <strong>{spec.persona_name || "this agent"}</strong>, register it, run onboarding and the capability checks, and activate it only if they pass and the governance rules allow it.</span></label>
                <ErrorBanner error={err} />
                <Button variant="primary" busy={busy === "create"} disabled={!canCreate || !confirmed || !pv?.validation?.ok || (strongDup && !dupChoice)} onClick={create}>Create agent</Button>
                {strongDup && !dupChoice && <p className="text-[12px] text-warning">Choose how to handle the similar agents in Review first.</p>}
              </> : <Result r={result} />}
            </div>
          )}
          <div className="mt-6 flex justify-between border-t border-line pt-3">
            <Button disabled={step === 0} onClick={() => goto(step - 1)}>← Back</Button>
            {step < STEPS.length - 1 && <Button variant="primary" onClick={() => goto(step + 1)}>Next: {STEPS[step + 1]} →</Button>}
          </div>
        </Card>
        <aside aria-label="Live preview" className="lg:sticky lg:top-4 lg:self-start">
          <Preview spec={spec} pv={pv} err={pvErr} />
        </aside>
      </div>
    </div>
  );
}

function Proposals({ d, onUse }: { d: any; onUse: (spec: any) => void }) {
  return (
    <div className="mt-3 grid gap-2 md:grid-cols-2" data-testid="design-proposals">
      {d.proposals.map((p: any) => (
        <div key={p.spec.persona_name} className="rounded-md border border-line bg-surface p-3 text-[12.5px]">
          <div className="flex items-center gap-2"><Sigil species={p.preview.species} name={p.spec.persona_name} size={36} /><span className="font-serif text-[14px] text-ink">{p.preview.display}</span></div>
          <p className="mt-1 text-ink-2">{p.spec.purpose}</p>
          <p className="mt-1 text-ink-3">{p.spec.traits.join(", ")} · {p.preview.department?.name ?? "—"} · {p.spec.rank}</p>
          {p.species_reason && <p className="mt-1"><ClassLabel kind="suggestion" /> {p.species_reason}</p>}
          <Button onClick={() => onUse(p.spec)}>Use this proposal</Button>
        </div>))}
      {d.duplicates?.length > 0 && <p className="text-[12px] text-warning md:col-span-2">Similar agents exist: {d.duplicates.slice(0, 3).map((x: any) => x.agent.display).join("; ")} — you decide in Review.</p>}
    </div>
  );
}

function SpeciesStep({ spec, set, errs, recs, ai }: { spec: Spec; set: (k: keyof Spec, v: any) => void; errs: Record<string, string>; recs: any[]; ai: React.ReactNode }) {
  const [q, setQ] = useState("");
  const [cat, setCat] = useState("");
  const list = useApi<any>(`/api/bestiary?q=${encodeURIComponent(q)}&category=${cat}&kind=being`, [q, cat]);
  const art = useApi<any>(spec.species_key ? `/api/bestiary/${spec.species_key}` : null, [spec.species_key]);
  const custom = !!spec.custom_species;
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-end gap-2">
        <label className="text-[11px] text-ink-3">Search The Bestiary<input type="search" className="mt-0.5 block" value={q} onChange={(e) => setQ(e.target.value)} placeholder="name or alternative name" /></label>
        <label className="text-[11px] text-ink-3">Type / origin group<select className="mt-0.5 block" value={cat} onChange={(e) => setCat(e.target.value)}>
          <option value="">All</option>{list.data?.categories.filter((c: any) => c.key !== "custom" || c.count).map((c: any) => <option key={c.key} value={c.key}>{c.name}</option>)}</select></label>
        {ai}
      </div>
      {recs.length > 0 && (
        <div className="rounded-md border border-cyan/40 p-2 text-[12px]" data-testid="species-recs">
          <div className="mb-1 text-cyan">Recommendations — not rules. Any species can do any job.</div>
          <ul className="space-y-1.5">{recs.slice(0, 4).map((r) => <li key={r.key}><button className="font-semibold text-ink underline decoration-dotted" onClick={() => { set("species_key", r.key); set("custom_species", null); }}>{r.name}</button>
            <ul className="mt-0.5 space-y-0.5">{r.reasons.map((x: any, n: number) => <li key={n} className="flex flex-wrap items-start gap-1.5"><ClassLabel kind={x.class} /><span className="text-ink-2">{x.text}</span></li>)}</ul></li>)}</ul>
        </div>)}
      {!custom && (
        <div role="radiogroup" aria-label="Species" className="grid max-h-[360px] gap-1.5 overflow-auto sm:grid-cols-2">
          {list.data?.species.map((s: any) => (
            <label key={s.key} className={`flex cursor-pointer items-center gap-2 rounded-md border p-1.5 text-[12.5px] ${spec.species_key === s.key ? "border-violet bg-violet/10" : "border-line"}`}>
              <input type="radio" name="species" className="sr-only" checked={spec.species_key === s.key} onChange={() => set("species_key", s.key)} />
              <Sigil species={s} name={s.name} size={30} /><span className="min-w-0"><span className="text-ink">{s.name}</span> <span className="text-[11px] text-ink-3">{s.origin}</span></span>
            </label>))}
          {list.data && !list.data.species.length && <div className="text-ink-3">No being matches.</div>}
        </div>)}
      {errs.species_key && <div className="text-[12px] text-warning">{errs.species_key}</div>}
      {art.data && !custom && (
        <div className="rounded-md border border-line p-3 text-[12.5px]">
          <div className="flex flex-wrap items-center gap-2"><span className="font-serif text-[15px] text-ink">{art.data.name}</span><Link className="text-[11.5px] text-ink-3 underline" href={`/bestiary/${art.data.key}`} target="_blank">read the article</Link></div>
          {art.data.folklore && <p className="mt-1 text-ink-2"><ClassLabel kind="folklore" /> {art.data.folklore}</p>}
          {art.data.canon && <p className="mt-1 text-ink-2"><ClassLabel kind="canon" /> {art.data.canon}</p>}
          {art.data.caution && <p className="mt-1 text-ink-3"><ClassLabel kind="caution" /> {art.data.caution}</p>}
          {art.data.subtype_articles?.length > 0 && <label className="mt-2 block text-[11px] text-ink-3">Subspecies<select className="mt-0.5 block" value={spec.subspecies} onChange={(e) => set("subspecies", e.target.value)}><option value="">—</option>{art.data.subtypes.map((x: string) => <option key={x}>{x}</option>)}</select></label>}
          {art.data.possible_specializations?.length > 0 && <div className="mt-2 flex flex-wrap items-center gap-1.5"><span className="text-ink-3">Suggested from The Bestiary:</span>
            {art.data.possible_specializations.map((x: any) => <button key={x.key} className="rounded border border-cyan/40 px-1.5 py-px text-cyan" onClick={() => set("specializations", spec.specializations.includes(x.key) ? spec.specializations : [...spec.specializations, x.key])}>+ {x.name}</button>)}</div>}
          {art.data.example_roles?.length > 0 && <div className="mt-1 text-ink-3">Example roles: {art.data.example_roles.map((r: string) => <button key={r} className="mr-2 underline decoration-dotted" onClick={() => set("title", r)}>{r}</button>)}</div>}
        </div>)}
      <details open={custom} className="text-[12.5px]"><summary className="cursor-pointer text-ink-2">Create my own fictional species instead</summary>
        <div className="mt-2 grid gap-2 sm:grid-cols-2">
          <input aria-label="Species name" placeholder="Species name" value={spec.custom_species?.name ?? ""} onChange={(e) => { set("custom_species", e.target.value ? { ...(spec.custom_species ?? {}), name: e.target.value } : null); if (e.target.value) set("species_key", ""); }} />
          <input aria-label="Species description" placeholder="What is this being like?" value={spec.custom_species?.description ?? ""} onChange={(e) => set("custom_species", { ...(spec.custom_species ?? { name: "" }), description: e.target.value })} />
        </div><p className="mt-1"><ClassLabel kind="user_created" /> <span className="text-ink-3">Marked as user-created in The Bestiary — your installation's canon, not folklore.</span></p></details>
    </div>
  );
}

function CustomSpec({ onAdd }: { onAdd: (name: string) => void }) {
  const [n, setN] = useState("");
  return <div className="flex gap-2"><input aria-label="Custom specialization" placeholder="Or name your own specialization" value={n} onChange={(e) => setN(e.target.value)} /><Button disabled={n.trim().length < 3} onClick={() => { onAdd(n.trim()); setN(""); }}>Add</Button></div>;
}

function Supervisor({ value, onChange, error }: { value: string; onChange: (v: string) => void; error?: string }) {
  const staff = useApi<any>("/api/personnel?sort=rank");
  return <label className="text-[11px] text-ink-3">Supervisor (reporting path to G-SUS)<select className="mt-0.5 w-full" value={value} onChange={(e) => onChange(e.target.value)} aria-invalid={!!error}>
    {staff.data?.agents.map((a: any) => <option key={a.id} value={a.id}>{a.persona_name} — {a.title}</option>)}</select>{error && <span className="text-warning">{error}</span>}</label>;
}

function Preview({ spec, pv, err }: { spec: Spec; pv: any; err: string | null }) {
  const species = pv?.species ?? (spec.custom_species ? { key: "custom", name: spec.custom_species.name, category: "custom" } : null);
  return (
    <section className="rounded-lg border border-violet/30 bg-surface p-4" data-testid="live-preview">
      <div className="mb-3 font-mono text-[10.5px] uppercase tracking-[0.16em] text-violet">Live preview</div>
      <div className="flex items-center gap-3"><Sigil species={species} name={spec.persona_name} size={64} />
        <div className="min-w-0"><div className="font-serif text-[16px] font-semibold text-ink [overflow-wrap:anywhere]" data-testid="preview-display">{pv?.display ?? (spec.persona_name || "Unnamed")}</div>
          <div className="text-[12px] text-ink-3">{spec.title || "No title yet"} · {pv?.rank ?? spec.rank}</div></div></div>
      {spec.traits.length > 0 && <div className="mt-3 flex flex-wrap gap-1">{spec.traits.map((t) => <span key={t} className="rounded-full border border-violet/40 px-2 py-px text-[11.5px] text-violet">{t}</span>)}</div>}
      <p className="mt-3 text-[12.5px] text-ink-2">{spec.description || spec.purpose || "Purpose not written yet."}</p>
      {spec.specializations.length > 0 && <div className="mt-2 text-[12px] text-cyan">{(pv?.specializations ?? spec.specializations.map((k) => ({ key: k, name: k }))).map((s: any) => s.name).join(" · ")}</div>}
      {spec.skills.length > 0 && <div className="mt-2 flex flex-wrap gap-1">{spec.skills.slice(0, 6).map((s) => <SkillChip key={s.name} s={s} />)}</div>}
      {spec.tool_suggestions.length > 0 && <div className="mt-2 text-[11.5px] text-ink-3">Suggested tools: {spec.tool_suggestions.join(", ")} (not access)</div>}
      <div className="mt-3 border-t border-line pt-2 text-[12px]">
        {err ? <span className="text-warning">{err}</span> : !pv ? <span className="text-ink-3">Validating…</span>
          : pv.validation.ok ? <span className="text-good">Valid · starts at level {pv.governance.starting_level}{pv.governance.needs_approval ? ` (level ${pv.governance.requested_level} needs approval)` : ""}</span>
            : <span className="text-warning">{pv.validation.errors.length} thing(s) to fix before creating</span>}
      </div>
    </section>
  );
}

function Result({ r }: { r: any }) {
  const st = useApi<any>(r.agent?.id && r.outcome === "created" ? `/api/personnel/agents/${r.agent.id}/status` : null, [r.agent?.id]);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => { ref.current?.focus(); }, []);
  return (
    <div ref={ref} tabIndex={-1} className="space-y-3 outline-none" data-testid="create-result">
      <div role="status" className={`rounded-md border px-3 py-2 ${r.agent?.lifecycle === "ACTIVE" || r.outcome !== "created" ? "border-good/40 bg-good/10 text-good" : "border-warning/40 bg-warning/10 text-warning"}`}>{r.message}</div>
      <div className="flex flex-wrap gap-2">
        {r.agent?.id && <Link className="rounded-md bg-violet px-3 py-1.5 text-[13px] font-semibold text-black" href={`/personnel/${r.agent.id}`}>Open {r.agent.persona_name}'s profile</Link>}
        {r.approval_id && <Link className="rounded-md border border-line-strong px-3 py-1.5 text-[13px] text-ink-2" href={`/approvals?id=${r.approval_id}`}>Approval #{r.approval_id}</Link>}
      </div>
      {r.steps?.length > 0 && <details open><summary className="cursor-pointer text-ink-2">Pipeline — {r.steps.length} steps</summary>
        <ol className="mt-1 space-y-0.5 text-[12px]">{r.steps.map((s: any) => <li key={s.n} className="flex flex-wrap items-center gap-1.5"><span className="num w-6 text-ink-3">{s.n}</span><StatusBadge status={s.status} /><span>{s.name}</span><span className="text-ink-3 [overflow-wrap:anywhere]">{s.detail}</span></li>)}</ol></details>}
      {st.data?.tests && <Tests t={st.data.tests} />}
    </div>
  );
}

export default function Page() {
  return <Suspense><Creator /></Suspense>;
}
