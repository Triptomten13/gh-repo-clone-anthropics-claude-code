"use client";
import { useState } from "react";
import { Button, Card, Empty, ErrorBanner, EVIDENCE_CLASSES, EvidenceBadge, Field, PageHeader, Stat, Table } from "@/components/ui";
import { ago, api } from "@/lib/api";
import { useApi } from "@/lib/hooks";

const SAMPLE = `{
  "works": [
    { "number": 1, "title": "Liber Primus", "chapters": [ { "number": 1, "title": "…", "summary": "…" } ] }
  ]
}`;

export default function Archivum() {
  const works = useApi<any>("/api/archivum/works");
  const contra = useApi<any[]>("/api/archivum/contradictions");
  const timeline = useApi<any[]>("/api/archivum/timeline");
  const assertions = useApi<any[]>("/api/archivum/assertions");
  const versions = useApi<any[]>("/api/archivum/versions");
  const [open, setOpen] = useState<number | null>(null);
  const work = useApi<any>(open ? `/api/archivum/works/${open}` : null, [open]);
  const [err, setErr] = useState<string | null>(null);
  const reload = () => { works.reload(); contra.reload(); timeline.reload(); assertions.reload(); versions.reload(); };
  const w = works.data;
  return (
    <>
      <PageHeader kicker="G-SUS · research & worldbuilding" title="Archivum Scientiae Vetitae" />
      <ErrorBanner error={err} />
      <p className="mb-4 max-w-3xl text-[13px] text-ink-3">The Archivum keeps documented history and internal mythology apart. Every assertion and date carries an evidentiary class;
        lore is <EvidenceBadge kind="fiction_canon" />, and canon is imported by its authors — the platform never writes it.</p>
      <div className="mb-4 grid grid-cols-2 gap-3 md:grid-cols-5">
        <Stat label="Books" value={w?.totals.works ?? "…"} /><Stat label="Chapters" value={w?.totals.chapters ?? "…"} />
        <Stat label="Assertions" value={assertions.data?.filter((a) => a.status === "active").length ?? "…"} />
        <Stat label="Contradictions" value={contra.data?.length ?? "…"} accent={!!contra.data?.length} />
        <Stat label="Canon version" value={versions.data?.[0]?.version ?? "—"} sub={versions.data?.[0]?.note} />
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        <Card title="Books & chapters">
          {w?.works?.length ? (
            <ul className="divide-y divide-line/60">{w.works.map((b: any) => (
              <li key={b.id} className="py-1.5"><button className="flex w-full justify-between text-left" onClick={() => setOpen(open === b.id ? null : b.id)}>
                <span className="font-serif text-[14px]"><span className="num text-ink-3">{String(b.number).padStart(2, "0")} </span>{b.title}</span><span className="text-[12px] text-ink-3">{b.chapters} ch · {b.status}</span></button>
                {open === b.id && work.data && <ol className="mt-1 space-y-0.5 pl-6 text-[12.5px]">{work.data.chapters.map((c: any) => <li key={c.id} className="text-ink-2"><span className="num text-ink-3">{c.number}.</span> {c.title} <span className="text-ink-3">{c.status}</span>{c.summary && <div className="text-[11.5px] text-ink-3">{c.summary}</div>}</li>)}</ol>}
              </li>))}</ul>
          ) : <Empty title="No canon structure stored">{w?.note}</Empty>}
          <ImportBox onDone={reload} onError={setErr} />
        </Card>
        <Card title="Contradictions">
          {contra.data?.length ? <ul className="space-y-2">{contra.data.map((c, i) => (
            <li key={i} className="rounded-md border border-serious/40 bg-serious/5 p-2.5 text-[12.5px]">
              <div className="font-mono text-[10.5px] uppercase text-serious">{c.type.replaceAll("_", " ")}</div>
              <div className="text-ink">{c.subject} · {c.predicate}</div>
              <ul className="mt-1 space-y-0.5">{c.values.map((v: any, j: number) => <li key={j} className="text-ink-2">“{v.object ?? v.date_text}” <EvidenceBadge kind={v.evidence_class} />{v.assertion_id && <button className="ml-2 text-[11px] text-violet hover:underline" onClick={async () => { await api(`/api/archivum/assertions/${v.assertion_id}/retire`, { method: "POST" }); reload(); }}>retire</button>}</li>)}</ul>
              <div className="mt-1 text-[11.5px] text-ink-3">{c.note}</div>
            </li>))}</ul> : <Empty title="No contradictions">Assertions and dates are checked whenever they are added.</Empty>}
        </Card>
      </div>

      <div className="mt-4 grid gap-4 xl:grid-cols-2">
        <Card title="Assertions (subject — predicate — object)" pad={false}>
          <AddAssertion onDone={reload} onError={setErr} />
          {assertions.data?.length ? <Table head={["Subject", "Predicate", "Object", "Evidence", "Status"]}>{assertions.data.map((a) => <tr key={a.id}><td>{a.subject}</td><td className="text-ink-3">{a.predicate}</td><td className="font-serif">{a.object}</td><td><EvidenceBadge kind={a.evidence_class} /></td><td className="text-ink-3">{a.status}</td></tr>)}</Table> : null}
        </Card>
        <Card title="Timeline">
          <AddEvent onDone={reload} onError={setErr} />
          {timeline.data?.length ? <ol className="relative mt-3 space-y-2 border-l border-line-strong pl-4">{timeline.data.map((e) => (
            <li key={e.id} className="text-[12.5px]"><span className="absolute -left-1 mt-1.5 h-2 w-2 rounded-full bg-gold" aria-hidden />
              <span className="num font-mono text-gold">{e.date_text}</span> <span className="font-serif text-ink">{e.label}</span> <EvidenceBadge kind={e.evidence_class} />
              {e.sort_year === null && <span className="text-[11px] text-ink-3"> (undated — not ordered)</span>}{e.description && <div className="text-ink-3">{e.description}</div>}</li>))}</ol>
            : <div className="mt-2 text-[12.5px] text-ink-3">No events yet.</div>}
        </Card>
      </div>
      <Card title="Canon versions" className="mt-4" pad={false}>
        {versions.data?.length ? <Table head={["Version", "Note", "By", "Assertions", "When"]}>{versions.data.map((v) => <tr key={v.id}><td className="num">{v.version}</td><td>{v.note}</td><td className="text-ink-3">{v.created_by}</td><td className="num">{v.assertions}</td><td className="text-ink-3">{ago(v.created_at)}</td></tr>)}</Table>
          : <div className="p-4 text-[12.5px] text-ink-3">No versions yet — every import creates one.</div>}
      </Card>
    </>
  );
}

function ImportBox({ onDone, onError }: { onDone: () => void; onError: (e: string) => void }) {
  const [text, setText] = useState("");
  const [works, setWorks] = useState("25");
  const [chapters, setChapters] = useState("260");
  const [res, setRes] = useState<any>(null);
  const go = async () => {
    try { setRes(await api("/api/archivum/import", { method: "POST", json: { data: JSON.parse(text), expected: { works: Number(works), chapters: Number(chapters) }, note: "import via UI" } })); onDone(); }
    catch (e) { onError((e as Error).message); }
  };
  return (
    <details className="mt-3 border-t border-line pt-3">
      <summary className="cursor-pointer text-[12.5px] text-violet">Import canon structure (admin)</summary>
      <textarea rows={6} className="mt-2 w-full font-mono text-[11.5px]" placeholder={SAMPLE} value={text} onChange={(e) => setText(e.target.value)} />
      <div className="mt-2 flex items-end gap-2"><Field label="Expected books"><input className="w-20" value={works} onChange={(e) => setWorks(e.target.value)} /></Field>
        <Field label="Expected chapters"><input className="w-20" value={chapters} onChange={(e) => setChapters(e.target.value)} /></Field><Button variant="primary" disabled={!text} onClick={go}>Import</Button></div>
      {res && <div className="mt-2 text-[12px] text-ink-2">Created {res.created.works} books, {res.created.chapters} chapters · totals {res.totals.works}/{res.totals.chapters} ·
        {Object.entries(res.structure_check).map(([k, v]: any) => <span key={k} className={v.ok ? "text-[#5fd35f]" : "text-warning"}> {k} {v.actual}/{v.expected} {v.ok ? "✓" : "≠"}</span>)} · canon v{res.canon_version}</div>}
    </details>
  );
}

function AddAssertion({ onDone, onError }: { onDone: () => void; onError: (e: string) => void }) {
  const [f, setF] = useState({ subject: "", predicate: "", object: "", evidence_class: "fiction_canon", source_note: "" });
  const [warn, setWarn] = useState<string | null>(null);
  const add = async () => {
    try { const r = await api<any>("/api/archivum/assertions", { method: "POST", json: f }); setWarn(r.conflicts.length ? `Conflicts with ${r.conflicts.length} existing assertion(s) — see Contradictions.` : null); setF({ ...f, object: "" }); onDone(); }
    catch (e) { onError((e as Error).message); }
  };
  return (
    <div className="grid grid-cols-2 gap-2 p-3 md:grid-cols-3">
      {(["subject", "predicate", "object"] as const).map((k) => <Field key={k} label={k}><input value={f[k]} onChange={(e) => setF({ ...f, [k]: e.target.value })} /></Field>)}
      <Field label="Evidence"><select value={f.evidence_class} onChange={(e) => setF({ ...f, evidence_class: e.target.value })}>{EVIDENCE_CLASSES.map((c) => <option key={c} value={c}>{c.replaceAll("_", " ")}</option>)}</select></Field>
      <Field label="Source (required for historical claims)"><input value={f.source_note} onChange={(e) => setF({ ...f, source_note: e.target.value })} /></Field>
      <div className="flex items-end"><Button variant="primary" disabled={!f.subject || !f.predicate || !f.object} onClick={add}>Add</Button></div>
      {warn && <div className="col-span-full text-[12px] text-warning">{warn}</div>}
    </div>
  );
}

function AddEvent({ onDone, onError }: { onDone: () => void; onError: (e: string) => void }) {
  const [f, setF] = useState({ label: "", date_text: "", evidence_class: "unclassified", source_note: "" });
  const add = async () => { try { await api("/api/archivum/timeline", { method: "POST", json: f }); setF({ ...f, label: "", date_text: "" }); onDone(); } catch (e) { onError((e as Error).message); } };
  return (
    <div className="flex flex-wrap items-end gap-2">
      <Field label="Event"><input value={f.label} onChange={(e) => setF({ ...f, label: e.target.value })} /></Field>
      <Field label="Date as stated"><input className="w-32" value={f.date_text} onChange={(e) => setF({ ...f, date_text: e.target.value })} placeholder="c. 587 BCE" /></Field>
      <Field label="Evidence"><select value={f.evidence_class} onChange={(e) => setF({ ...f, evidence_class: e.target.value })}>{EVIDENCE_CLASSES.map((c) => <option key={c} value={c}>{c.replaceAll("_", " ")}</option>)}</select></Field>
      <Button disabled={!f.label || !f.date_text} onClick={add}>Add</Button>
    </div>
  );
}
