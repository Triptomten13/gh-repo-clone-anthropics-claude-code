"use client";
import { useDialog } from "@/components/dialog";
import { Fragment, useEffect, useState } from "react";
import { GraphView } from "@/components/flare";
import { Button, Card, Empty, ErrorBanner, EVIDENCE_CLASSES, EvidenceBadge, Field, PageHeader, Stat, StatusBadge, Table } from "@/components/ui";
import { ago, api, API_URL, getToken } from "@/lib/api";
import { useApi } from "@/lib/hooks";

const TABS = [["search", "Search"], ["ask", "Ask the Archive"], ["documents", "Documents"], ["entities", "Entities & graph"], ["memory", "Memory"]] as const;

export default function ArchivePage() {
  const [tab, setTab] = useState<string>("search");
  const [docId, setDocId] = useState<number | null>(null);
  const stats = useApi<any>("/api/archive/stats");
  useEffect(() => {
    const h = window.location.hash;
    const m = /^#doc-(\d+)$/.exec(h);
    if (m) { setTab("documents"); setDocId(Number(m[1])); } else if (h.length > 1) setTab(h.slice(1));
  }, []);
  const pick = (t: string) => { setTab(t); history.replaceState(null, "", `#${t}`); };
  const s = stats.data;
  return (
    <>
      <PageHeader kicker="G-SUS · memory" title="The Archive">
        {(s || stats.loading) && <span className="text-[12px] text-ink-3">embeddings: <code>{s?.embedding_model ?? "…"}</code></span>}
      </PageHeader>
      {(s || stats.loading) && ( /* rendered at once with placeholders: the tabs below must not jump when the numbers arrive */
        <div className="mb-4 grid grid-cols-2 gap-3 md:grid-cols-5">
          <Stat label="Documents" value={s?.documents ?? "…"} sub={s ? Object.entries(s.by_status).map(([k, v]) => `${v} ${k}`).join(" · ") || "\u00a0" : "\u00a0"} />
          <Stat label="Indexed passages" value={s?.chunks ?? "…"} />
          <Stat label="Entities" value={s?.entities ?? "…"} />
          <Stat label="Instruction-like content" value={s?.injection_flagged ?? "…"} sub="documents flagged (treated as data)" />
          <Stat label="Evidence classes" value={s ? Object.keys(s.by_evidence_class).length : "…"} sub="in use" />
        </div>
      )}
      <div role="tablist" className="mb-4 flex flex-wrap gap-1">
        {TABS.map(([id, name]) => <button key={id} role="tab" aria-selected={tab === id} onClick={() => pick(id)}
          className={`rounded-md border px-3 py-1 text-[12.5px] ${tab === id ? "border-violet bg-violet/10 text-ink" : "border-line text-ink-3 hover:text-ink-2"}`}>{name}</button>)}
      </div>
      {tab === "search" ? <SearchTab /> : tab === "ask" ? <AskTab /> : tab === "documents" ? <DocumentsTab docId={docId} setDocId={setDocId} onChange={stats.reload} />
        : tab === "entities" ? <EntitiesTab /> : <MemoryTab />}
    </>
  );
}

function SearchTab() {
  const [q, setQ] = useState("");
  const [mode, setMode] = useState("hybrid");
  const [ev, setEv] = useState("");
  const [res, setRes] = useState<any[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const go = async () => {
    try { setRes((await api<any>("/api/archive/search", { method: "POST", json: { query: q, mode, filters: ev ? { evidence_class: ev } : {} } })).results); setErr(null); }
    catch (e) { setErr((e as Error).message); }
  };
  return (
    <Card>
      <form className="flex flex-wrap gap-2" onSubmit={(e) => { e.preventDefault(); if (q) go(); }}>
        <input className="w-full flex-1 sm:w-auto sm:min-w-80" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search passages (full-text + vectors)…" aria-label="search query" />
        <select value={mode} onChange={(e) => setMode(e.target.value)} aria-label="mode"><option value="hybrid">hybrid</option><option value="keyword">keyword (BM25)</option><option value="semantic">vector</option></select>
        <select value={ev} onChange={(e) => setEv(e.target.value)} aria-label="evidence filter"><option value="">any evidence class</option>{EVIDENCE_CLASSES.map((c) => <option key={c} value={c}>{c.replaceAll("_", " ")}</option>)}</select>
        <Button variant="primary" type="submit" disabled={!q}>Search</Button>
      </form>
      <ErrorBanner error={err} />
      {res === null ? null : res.length === 0 ? <div className="mt-4"><Empty title="No relevant passages">Below the relevance floor nothing is returned — better nothing than noise.</Empty></div> : (
        <ol className="mt-4 space-y-3">{res.map((h) => (
          <li key={h.chunk_id} className="rounded-md border border-line bg-bg/50 p-3">
            <div className="flex flex-wrap items-center gap-2 text-[12.5px]"><b className="font-serif text-[14px] text-ink">{h.title}</b><span className="font-mono text-[11px] text-ink-3">{h.citation}{h.page ? ` p.${h.page}` : ""}</span>
              <EvidenceBadge kind={h.evidence_class} />{h.injection_risk && <span className="text-[11px] text-warning">⚠ instruction-like text — data, not instructions</span>}<span className="num ml-auto text-[11px] text-ink-3">score {h.score}</span></div>
            <p className="mt-1 font-serif text-[13.5px] text-ink-2">{h.snippet}</p>
            <div className="text-[11px] text-ink-3">{[h.author, h.created_date, h.source].filter(Boolean).join(" · ")}{h.source_url && <> · <a className="text-violet hover:underline" href={h.source_url} target="_blank" rel="noreferrer noopener">source ↗</a></>}</div>
          </li>))}</ol>
      )}
    </Card>
  );
}

function AskTab() {
  const [q, setQ] = useState("");
  const [useLlm, setUseLlm] = useState(false);
  const [ans, setAns] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const ask = async () => {
    setBusy(true);
    try { setAns(await api("/api/archive/ask", { method: "POST", json: { question: q, use_llm: useLlm } })); setErr(null); } catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  };
  return (
    <Card title="The Archivist answers only from the Archive">
      <div className="flex flex-wrap gap-2">
        <input className="w-full flex-1 sm:w-auto sm:min-w-80" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Ask a question…" aria-label="question" />
        <label className="flex items-center gap-1.5 text-[12px] text-ink-3"><input type="checkbox" checked={useLlm} onChange={(e) => setUseLlm(e.target.checked)} /> phrase with AI (citations verified)</label>
        <Button variant="primary" busy={busy} disabled={!q} onClick={ask}>Ask</Button>
      </div>
      <ErrorBanner error={err} />
      {ans && (
        <div className="mt-4">
          <div className="mb-2 flex flex-wrap gap-2 text-[11.5px] text-ink-3"><span>method: <b className="text-ink-2">{ans.method}</b></span>
            <span>grounded: <b className={ans.grounding?.supported ? "text-[#5fd35f]" : "text-warning"}>{String(ans.grounding?.supported)}</b></span>
            {ans.grounding?.invalid_citations?.length > 0 && <span className="text-[#f08a8a]">rejected invented citations: {ans.grounding.invalid_citations.join(", ")}</span>}</div>
          <pre className="whitespace-pre-wrap rounded-md bg-bg p-3 font-serif text-[13.5px] leading-relaxed text-ink-2">{ans.answer}</pre>
          <ol className="mt-3 space-y-1">{ans.citations.map((c: any) => <li key={c.n} className="text-[12px]"><span className="num text-ink-3">[{c.n}]</span> {c.title} §{c.ordinal} <EvidenceBadge kind={c.evidence_class} /></li>)}</ol>
        </div>
      )}
    </Card>
  );
}

function DocumentsTab({ docId, setDocId, onChange }: { docId: number | null; setDocId: (n: number | null) => void; onChange: () => void }) {
  const [ev, setEv] = useState("");
  const docs = useApi<any[]>(`/api/archive/documents${ev ? `?evidence_class=${ev}` : ""}`, [ev]);
  const [err, setErr] = useState<string | null>(null);
  return (
    <div className="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
      <div className="space-y-4">
        <AddDocument onDone={(id) => { docs.reload(); onChange(); setDocId(id); }} onError={setErr} />
        <ErrorBanner error={err} />
        <Card title="Documents" action={<select value={ev} onChange={(e) => setEv(e.target.value)} aria-label="evidence filter"><option value="">all classes</option>{EVIDENCE_CLASSES.map((c) => <option key={c} value={c}>{c.replaceAll("_", " ")}</option>)}</select>} pad={false}>
          {docs.data?.length ? (
            <Table head={["Title", "Type", "Evidence", "Status", "v", "Imported"]}>
              {docs.data.map((d) => (
                <tr key={d.id} className={docId === d.id ? "bg-surface-2" : ""}>
                  <td><button className="text-left font-serif text-[13.5px] hover:text-violet" onClick={() => setDocId(d.id)}>{d.title}</button>{d.injection_flags?.length > 0 && <span className="ml-1 text-[11px] text-warning" title={d.injection_flags.join(", ")}>⚠</span>}</td>
                  <td className="text-ink-3">{d.doc_type}</td><td><EvidenceBadge kind={d.evidence_class} /></td>
                  <td><StatusBadge status={d.status === "ready" ? "succeeded" : d.status === "duplicate" ? "cancelled" : d.status === "failed" ? "failed" : "running"} /> <span className="text-[11px] text-ink-3">{d.status}</span></td>
                  <td className="num">{d.version}</td><td className="text-ink-3">{ago(d.imported_at)}</td>
                </tr>
              ))}
            </Table>
          ) : <div className="p-4"><Empty title="The Archive is empty">Upload PDF, DOCX, TXT, Markdown, CSV, JSON or transcripts — or paste text. Nothing is pre-filled.</Empty></div>}
        </Card>
      </div>
      {docId ? <DocumentDetail id={docId} onChange={() => { docs.reload(); onChange(); }} onClose={() => setDocId(null)} /> : <Card><Empty title="Select a document" /></Card>}
    </div>
  );
}

function AddDocument({ onDone, onError }: { onDone: (id: number) => void; onError: (e: string) => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [text, setText] = useState("");
  const [m, setM] = useState({ title: "", source: "", source_url: "", author: "", created_date: "", tags: "", evidence_class: "unclassified", description: "" });
  const [busy, setBusy] = useState(false);
  const submit = async () => {
    setBusy(true);
    try {
      let doc: any;
      if (file) {
        const fd = new FormData(); fd.append("file", file);
        for (const [k, v] of Object.entries(m)) fd.append(k, v);
        const res = await fetch(`${API_URL}/api/archive/upload`, { method: "POST", headers: { Authorization: `Bearer ${getToken()}` }, body: fd });
        doc = await res.json(); if (!res.ok) throw new Error(doc.detail ?? res.statusText);
      } else {
        doc = await api("/api/archive/text", { method: "POST", json: { ...m, text, tags: m.tags.split(",").map((t) => t.trim()).filter(Boolean) } });
      }
      setFile(null); setText(""); onDone(doc.id);
    } catch (e) { onError((e as Error).message); } finally { setBusy(false); }
  };
  return (
    <Card title="Add to the Archive (provenance required)">
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        <Field label="File (pdf, docx, txt, md, csv, json, vtt, srt, images)"><input type="file" accept=".pdf,.docx,.txt,.md,.csv,.json,.vtt,.srt,.png,.jpg,.jpeg,.webp" onChange={(e) => setFile(e.target.files?.[0] ?? null)} /></Field>
        <Field label="Evidentiary status">
          <select value={m.evidence_class} onChange={(e) => setM({ ...m, evidence_class: e.target.value })}>{EVIDENCE_CLASSES.map((c) => <option key={c} value={c}>{c.replaceAll("_", " ")}</option>)}</select>
        </Field>
        {(["title", "source", "source_url", "author", "created_date", "tags"] as const).map((k) => <Field key={k} label={k.replace("_", " ")}><input value={m[k]} onChange={(e) => setM({ ...m, [k]: e.target.value })} placeholder={k === "created_date" ? "e.g. c. 200 BCE" : ""} /></Field>)}
      </div>
      {!file && <Field label="…or paste text"><textarea rows={4} value={text} onChange={(e) => setText(e.target.value)} /></Field>}
      <div className="mt-2 flex items-center gap-2"><Button variant="primary" busy={busy} disabled={!file && !(text && m.title)} onClick={submit}>Ingest</Button>
        <span className="text-[11.5px] text-ink-3">Unsure of the status? Choose “unclassified” — never guess “historical fact”.</span></div>
    </Card>
  );
}

function DocumentDetail({ id, onChange, onClose }: { id: number; onChange: () => void; onClose: () => void }) {
  const d = useApi<any>(`/api/archive/documents/${id}`, [id]);
  const [note, setNote] = useState({ text: "", kind: "interpretation", evidence_class: "religious_interpretation" });
  const [err, setErr] = useState<string | null>(null);
  const dlg = useDialog();
  const x = d.data;
  if (!x) return <ErrorBanner error={d.error} />;
  const patch = async (body: any) => { try { await api(`/api/archive/documents/${id}`, { method: "PATCH", json: body }); d.reload(); onChange(); } catch (e) { setErr((e as Error).message); } };
  const annotate = async () => { try { await api(`/api/archive/documents/${id}/annotations`, { method: "POST", json: note }); setNote({ ...note, text: "" }); d.reload(); } catch (e) { setErr((e as Error).message); } };
  const del = async () => { if (!(await dlg.confirm({ title: `Delete "${x.title}"?`, message: "The document, its chunks, annotations and relations are removed permanently. This cannot be undone.", confirmLabel: "Delete permanently", danger: true }))) return; try { await api(`/api/archive/documents/${id}?confirm=true`, { method: "DELETE" }); onChange(); onClose(); } catch (e) { setErr((e as Error).message); } };
  return (
    <Card title={x.title} action={<span className="font-mono text-[10.5px] text-ink-3">{x.uid.slice(0, 8)} · v{x.version}</span>}>
      <ErrorBanner error={err} />
      <div className="flex flex-wrap items-center gap-2 text-[12px]">
        <EvidenceBadge kind={x.evidence_class} />
        <select value={x.evidence_class} onChange={(e) => patch({ evidence_class: e.target.value })} aria-label="change evidence class">{EVIDENCE_CLASSES.map((c) => <option key={c} value={c}>{c.replaceAll("_", " ")}</option>)}</select>
        <span className="text-ink-3">{x.doc_type} · {x.char_count.toLocaleString()} chars · {x.chunks} passages</span>
      </div>
      <dl className="mt-2 grid grid-cols-[100px_minmax(0,1fr)] gap-y-0.5 text-[12px]">
        {[["Source", x.source], ["Author", x.author], ["Dated", x.created_date], ["Imported", new Date(x.imported_at).toLocaleString()], ["Tags", (x.tags ?? []).join(", ")]].map(([k, v]) => <Fragment key={k}><dt className="text-ink-3">{k}</dt><dd className="text-ink-2">{v || "—"}</dd></Fragment>)}
      </dl>
      {x.error && <div className="mt-2 text-[12px] text-warning">{x.error}</div>}
      {x.injection_flags?.length > 0 && <div className="mt-2 rounded border border-warning/40 bg-warning/5 px-2 py-1 text-[12px] text-warning">Contains instruction-like text ({x.injection_flags.join(", ")}). It is shown and cited as data only; models are told never to follow it.</div>}
      {x.entities.length > 0 && <div className="mt-3 flex flex-wrap gap-1">{x.entities.map((e: any) => <span key={e.id} className="rounded border border-line px-1.5 py-px text-[11px] text-ink-2">{e.name} <span className="text-ink-3">{e.kind} ×{e.mentions}</span></span>)}</div>}
      {x.relations.length > 0 && <ul className="mt-3 space-y-0.5 text-[12px] text-ink-2">{x.relations.map((r: any) => <li key={r.id}>{r.relation.replace("_", " ")} → {r.other_title} <span className="text-ink-3">{r.note}</span></li>)}</ul>}
      {x.related.length > 0 && <div className="mt-2 text-[12px] text-ink-3">Related: {x.related.map((r: any) => `${r.title} (${r.shared_entities} shared)`).join(" · ")}</div>}
      {x.versions.length > 1 && <div className="mt-2 text-[12px] text-ink-3">Versions: {x.versions.map((v: any) => `v${v.version}`).join(" → ")}</div>}
      <div className="mt-4 font-mono text-[10.5px] uppercase tracking-[0.14em] text-gold">Source text (passages)</div>
      <ol className="mt-1 max-h-72 space-y-2 overflow-auto pr-1">{x.chunks_page.map((c: any) => <li key={c.id} className="font-serif text-[13px] text-ink-2"><span className="font-mono text-[10.5px] text-ink-3">§{c.ordinal}{c.page ? ` p.${c.page}` : ""} </span>{c.text}</li>)}</ol>
      <div className="mt-4 font-mono text-[10.5px] uppercase tracking-[0.14em] text-violet">Interpretations & notes (kept apart from the source)</div>
      <ul className="mt-1 space-y-1.5">{x.annotations.map((a: any) => <li key={a.id} className="text-[12.5px]"><EvidenceBadge kind={a.evidence_class} /> <span className="text-ink-3">{a.kind} · {a.author}</span><div className="text-ink-2">{a.text}</div></li>)}</ul>
      <div className="mt-2 flex flex-wrap gap-2">
        <input className="w-full flex-1 sm:w-auto sm:min-w-60" value={note.text} onChange={(e) => setNote({ ...note, text: e.target.value })} placeholder="Add an interpretation or note…" aria-label="annotation" />
        <select value={note.kind} onChange={(e) => setNote({ ...note, kind: e.target.value })} aria-label="Annotation kind"><option>interpretation</option><option>note</option><option>source_comparison</option><option>correction</option></select>
        <select value={note.evidence_class} onChange={(e) => setNote({ ...note, evidence_class: e.target.value })} aria-label="Annotation evidence class">{EVIDENCE_CLASSES.map((c) => <option key={c} value={c}>{c.replaceAll("_", " ")}</option>)}</select>
        <Button disabled={!note.text} onClick={annotate}>Add</Button>
      </div>
      <div className="mt-4 border-t border-line pt-3"><Button variant="danger" onClick={del}>Delete document (admin)</Button></div>
    </Card>
  );
}

function EntitiesTab() {
  const ents = useApi<any[]>("/api/archive/entities");
  const g = useApi<any>("/api/archive/graph");
  return (
    <div className="grid grid-cols-1 gap-4 xl:grid-cols-[360px_minmax(0,1fr)]">
      <Card title="Entities" pad={false}>
        {ents.data?.length ? <Table head={["Name", "Kind", "Docs"]}>{ents.data.map((e) => <tr key={e.id}><td className="font-serif">{e.name}</td><td className="text-ink-3">{e.kind}</td><td className="num">{e.documents}</td></tr>)}</Table>
          : <div className="p-4"><Empty title="No entities yet">Entities are linked from a curated gazetteer when documents are ingested.</Empty></div>}
      </Card>
      <Card title="Knowledge graph · documents ↔ entities">
        {g.data?.nodes?.length ? <GraphView nodes={[{ key: "product", label: "Archive", kind: "product" }, ...g.data.nodes]} edges={[...g.data.nodes.filter((n: any) => n.kind === "document").map((n: any) => ({ source: "product", target: n.key, relation: "holds" })), ...g.data.edges]} height={520} />
          : <Empty title="No graph yet" />}
      </Card>
    </div>
  );
}

const SCOPES = ["user_preference", "project", "long_term", "session", "agent_working", "creative_canon", "external_retrieved"];

function MemoryTab() {
  const [scope, setScope] = useState("");
  const items = useApi<any[]>(`/api/memory${scope ? `?scope=${scope}` : ""}`, [scope]);
  const [f, setF] = useState({ scope: "user_preference", key: "", content: "", expires_in_days: "" });
  const [err, setErr] = useState<string | null>(null);
  const [pending, setPending] = useState<any>(null);
  const add = async (allow = false) => {
    try {
      await api("/api/memory", { method: "POST", json: { ...f, expires_in_days: f.expires_in_days ? Number(f.expires_in_days) : null, allow_personal: allow } });
      setF({ ...f, key: "", content: "" }); setPending(null); setErr(null); items.reload();
    } catch (e) { const msg = (e as Error).message; if (msg.includes("allow_personal")) setPending(msg); else setErr(msg); }
  };
  const del = async (id: number) => { await api(`/api/memory/${id}`, { method: "DELETE" }); items.reload(); };
  const exportAll = async () => {
    const data = await api("/api/memory/export");
    const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }));
    const a = document.createElement("a"); a.href = url; a.download = "gsus-memory-export.json"; a.click(); URL.revokeObjectURL(url);
  };
  return (
    <div className="grid grid-cols-1 gap-4 xl:grid-cols-[380px_minmax(0,1fr)]">
      <Card title="Remember something">
        <p className="mb-2 text-[12px] text-ink-3">Your memory is private to you. It never stores passwords, keys, personal identity or card numbers; you can edit, export and delete everything.</p>
        <div className="space-y-2">
          <Field label="Scope"><select value={f.scope} onChange={(e) => setF({ ...f, scope: e.target.value })}>{SCOPES.map((s) => <option key={s} value={s}>{s.replaceAll("_", " ")}</option>)}</select></Field>
          <Field label="Key"><input value={f.key} onChange={(e) => setF({ ...f, key: e.target.value })} /></Field>
          <Field label="Content"><textarea rows={3} value={f.content} onChange={(e) => setF({ ...f, content: e.target.value })} /></Field>
          <Field label="Expires after (days, optional)"><input type="number" value={f.expires_in_days} onChange={(e) => setF({ ...f, expires_in_days: e.target.value })} /></Field>
          <Button variant="primary" disabled={!f.key || !f.content} onClick={() => add(false)}>Save</Button>
          {pending && <div className="rounded border border-warning/40 p-2 text-[12px] text-warning">{pending}<div className="mt-1"><Button onClick={() => add(true)}>Store anyway</Button></div></div>}
          <ErrorBanner error={err} />
        </div>
      </Card>
      <Card title="Your memory" action={<span className="flex gap-2"><select value={scope} onChange={(e) => setScope(e.target.value)} aria-label="scope filter"><option value="">all scopes</option>{SCOPES.map((s) => <option key={s} value={s}>{s.replaceAll("_", " ")}</option>)}</select><Button onClick={exportAll}>Export JSON</Button></span>} pad={false}>
        {items.data?.length ? <Table head={["Scope", "Key", "Content", "Updated", ""]}>{items.data.map((m) => <tr key={m.id}><td className="text-ink-3">{m.scope.replaceAll("_", " ")}</td><td>{m.key}</td><td className="max-w-md text-[12.5px] text-ink-2">{m.content}</td><td className="text-ink-3">{ago(m.updated_at)}</td><td><Button variant="danger" onClick={() => del(m.id)}>Delete</Button></td></tr>)}</Table>
          : <div className="p-4"><Empty title="Nothing remembered" /></div>}
      </Card>
    </div>
  );
}
