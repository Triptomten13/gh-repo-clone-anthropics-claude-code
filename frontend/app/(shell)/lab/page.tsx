"use client";
import Link from "next/link";
import { useMemo, useState } from "react";
import { Button, Card, DemoBadge, Empty, ErrorBanner, Field, PageHeader, ScoreBar, StatusBadge, Table } from "@/components/ui";
import { api, pct, sek } from "@/lib/api";
import { useApi, useRefreshOn } from "@/lib/hooks";

type P = { id: number; name: string; category: string; status: string; compliance_status: string; opportunity_score: number | null; score_confidence: number | null;
  wholesale_price: number | null; retail_price: number | null; net_margin: number | null; trend_velocity: number | null; source_platform: string; is_demo: boolean; platforms_seen: string[] };

const NUMERIC = ["wholesale_price", "shipping_cost", "retail_price", "delivery_days", "purchase_signal", "engagement_signal", "search_interest",
  "competitor_count", "competition_quality", "customization_potential", "differentiation_potential", "marketing_potential", "scalability", "return_risk"] as const;

export default function LabPage() {
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");
  const [minScore, setMinScore] = useState("");
  const path = useMemo(() => {
    const s = new URLSearchParams();
    if (q) s.set("q", q);
    if (status) s.set("status", status);
    if (minScore) s.set("min_score", minScore);
    return `/api/products?${s}`;
  }, [q, status, minScore]);
  const prods = useApi<P[]>(path, [path]);
  useRefreshOn(["task"], prods.reload);
  const [err, setErr] = useState<string | null>(null);
  const [showAdd, setShowAdd] = useState(false);
  const [showImport, setShowImport] = useState(false);
  const [compare, setCompare] = useState<number[]>([]);

  const evaluateAll = async () => {
    try { await api("/api/tasks", { method: "POST", json: { type: "ceo.evaluate_pipeline", payload: { limit: 50 }, force: true } }); }
    catch (e) { setErr((e as Error).message); }
  };
  const list = prods.data ?? [];
  const cmp = list.filter((p) => compare.includes(p.id));

  return (
    <>
      <PageHeader kicker="Product laboratory" title="Opportunity database">
        <Button onClick={() => setShowImport((v) => !v)}>Import CSV / JSON</Button>
        <Button onClick={() => setShowAdd((v) => !v)}>Add product</Button>
        <Button variant="primary" onClick={evaluateAll}>Evaluate pipeline</Button>
      </PageHeader>
      <ErrorBanner error={err || prods.error} />
      {showAdd && <AddProduct onDone={() => { setShowAdd(false); prods.reload(); }} onError={setErr} />}
      {showImport && <ImportBox onDone={() => { setShowImport(false); prods.reload(); }} onError={setErr} />}

      <div className="mb-3 flex flex-wrap items-end gap-3">
        <Field label="Search"><input value={q} onChange={(e) => setQ(e.target.value)} placeholder="name or description" /></Field>
        <Field label="Status">
          <select value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="">any</option>{["discovered", "investigating", "validated", "launched", "discontinued", "rejected"].map((s) => <option key={s}>{s}</option>)}
          </select>
        </Field>
        <Field label="Min score"><input type="number" className="w-24" value={minScore} onChange={(e) => setMinScore(e.target.value)} /></Field>
      </div>

      {cmp.length >= 2 && (
        <Card title={`Comparing ${cmp.length} products`} className="mb-4" action={<button className="text-[12px] text-ink-3 hover:text-ink" onClick={() => setCompare([])}>clear</button>}>
          <Table head={["", ...cmp.map((p) => p.name)]}>
            {([["Score", (p: P) => p.opportunity_score?.toFixed(0) ?? "—"], ["Data coverage", (p: P) => pct(p.score_confidence)], ["Net margin (after assumed CAC)", (p: P) => pct(p.net_margin)],
              ["Wholesale", (p: P) => sek(p.wholesale_price)], ["Retail", (p: P) => sek(p.retail_price)], ["Trend velocity", (p: P) => p.trend_velocity?.toFixed(0) ?? "—"],
              ["Compliance", (p: P) => <StatusBadge status={p.compliance_status} />]] as const).map(([label, f]) => (
              <tr key={label}><td className="text-ink-3">{label}</td>{cmp.map((p) => <td key={p.id} className="num">{f(p)}</td>)}</tr>
            ))}
          </Table>
        </Card>
      )}

      <Card pad={false}>
        {list.length ? (
          <Table head={["", "Product", "Category", "Score · coverage", "Net margin", "Trend", "Wholesale", "Retail", "Compliance", "Status", "Source"]}>
            {list.map((p) => (
              <tr key={p.id}>
                <td><input type="checkbox" aria-label="compare" checked={compare.includes(p.id)} onChange={(e) => setCompare((c) => e.target.checked ? [...c, p.id] : c.filter((x) => x !== p.id))} /></td>
                <td className="max-w-72 truncate font-medium"><Link className="hover:text-violet" href={`/lab/${p.id}`}>{p.name}</Link><DemoBadge show={p.is_demo} /></td>
                <td className="text-ink-2">{p.category || "—"}</td>
                <td><ScoreBar score={p.opportunity_score} confidence={p.score_confidence} /></td>
                <td className="num">{pct(p.net_margin)}</td>
                <td className="num">{p.trend_velocity?.toFixed(0) ?? "—"}</td>
                <td className="num">{sek(p.wholesale_price)}</td>
                <td className="num">{sek(p.retail_price)}</td>
                <td><StatusBadge status={p.compliance_status} /></td>
                <td className="text-ink-2">{p.status}</td>
                <td className="text-ink-3">{p.source_platform}</td>
              </tr>
            ))}
          </Table>
        ) : <div className="p-4"><Empty title="No products">Add a product, import a licensed dataset, or configure a research connector and run a market scan.</Empty></div>}
      </Card>
    </>
  );
}

function AddProduct({ onDone, onError }: { onDone: () => void; onError: (e: string) => void }) {
  const [f, setF] = useState<Record<string, string>>({ name: "", category: "", description: "", tags: "", competitor_prices: "" });
  const [busy, setBusy] = useState(false);
  const submit = async (e: React.FormEvent) => {
    e.preventDefault(); setBusy(true);
    const body: Record<string, unknown> = { name: f.name, category: f.category, description: f.description,
      tags: f.tags.split(",").map((s) => s.trim()).filter(Boolean), competitor_prices: f.competitor_prices.split(",").map(Number).filter((n) => n > 0) };
    for (const k of NUMERIC) if (f[k]) body[k] = Number(f[k]);
    try { await api("/api/products", { method: "POST", json: body }); onDone(); } catch (err) { onError((err as Error).message); } finally { setBusy(false); }
  };
  return (
    <Card title="New product (leave unknown values empty — they lower confidence instead of being guessed)" className="mb-4">
      <form onSubmit={submit} className="grid grid-cols-2 gap-3 md:grid-cols-4 lg:grid-cols-6">
        {["name", "category", "tags", "competitor_prices"].map((k) => (
          <Field key={k} label={k.replace("_", " ") + (k === "tags" || k === "competitor_prices" ? " (comma sep.)" : "")}>
            <input required={k === "name"} value={f[k] ?? ""} onChange={(e) => setF({ ...f, [k]: e.target.value })} />
          </Field>
        ))}
        {NUMERIC.map((k) => (
          <Field key={k} label={k.replaceAll("_", " ") + (k.endsWith("price") || k === "shipping_cost" ? " (SEK)" : k === "return_risk" ? " (0–1)" : k.includes("days") || k.includes("count") ? "" : " (0–100)")}>
            <input type="number" step="any" value={f[k] ?? ""} onChange={(e) => setF({ ...f, [k]: e.target.value })} />
          </Field>
        ))}
        <div className="col-span-full"><Field label="description"><textarea rows={2} value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} /></Field></div>
        <div className="col-span-full"><Button variant="primary" type="submit" busy={busy}>Save product</Button></div>
      </form>
    </Card>
  );
}

function ImportBox({ onDone, onError }: { onDone: () => void; onError: (e: string) => void }) {
  const [kind, setKind] = useState("products");
  const [format, setFormat] = useState("csv");
  const [content, setContent] = useState("");
  const [busy, setBusy] = useState(false);
  const submit = async () => {
    setBusy(true);
    try { await api(`/api/import/${kind}`, { method: "POST", json: { format, content } }); onDone(); } catch (e) { onError((e as Error).message); } finally { setBusy(false); }
  };
  return (
    <Card title="Import licensed or first-party data" className="mb-4">
      <div className="mb-3 flex flex-wrap gap-3">
        <Field label="Dataset"><select value={kind} onChange={(e) => setKind(e.target.value)}><option value="products">products</option><option value="observations">trend observations</option><option value="ledger">ledger entries</option></select></Field>
        <Field label="Format"><select value={format} onChange={(e) => setFormat(e.target.value)}><option>csv</option><option>json</option></select></Field>
        <Field label="File"><input type="file" accept=".csv,.json" onChange={async (e) => { const file = e.target.files?.[0]; if (file) setContent(await file.text()); }} /></Field>
      </div>
      <textarea rows={6} className="w-full font-mono" value={content} onChange={(e) => setContent(e.target.value)}
        placeholder={kind === "products" ? "name,category,wholesale_price,retail_price,competitor_prices,tags\nBamboo desk organiser,office,45,299,249|299|349,giftable" :
          kind === "observations" ? "keyword,platform,metric,value,observed_at\nsourdough,google_trends,search_interest,64,2026-10-01" : "kind,amount,occurred_at,product_id,channel\nrevenue,449,2026-10-01,1,shopify"} />
      <div className="mt-3"><Button variant="primary" busy={busy} disabled={!content} onClick={submit}>Import</Button></div>
    </Card>
  );
}
