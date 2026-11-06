"use client";
import Link from "next/link";
import { useState } from "react";
import { RevenueProfitChart } from "@/components/charts";
import { Button, Card, Empty, ErrorBanner, Field, Json, PageHeader, Stat, Table } from "@/components/ui";
import { api, fmt, pct, sek } from "@/lib/api";
import { useApi, useRefreshOn } from "@/lib/hooks";

export default function FinancePage() {
  const [days, setDays] = useState(90);
  const sum = useApi<any>(`/api/finance/summary?days=${days}`, [days]);
  const fc = useApi<any>("/api/finance/forecast");
  const prods = useApi<any[]>("/api/products");
  useRefreshOn(["task"], () => { sum.reload(); fc.reload(); });
  const [capital, setCapital] = useState("");
  const [alloc, setAlloc] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);
  const names = new Map((prods.data ?? []).map((p) => [String(p.id), p.name]));
  const s = sum.data;

  const allocate = async () => {
    try {
      const t = await api("/api/tasks", { method: "POST", json: { type: "finance.capital_allocation", payload: { available_sek: Number(capital) }, force: true } });
      setTimeout(async () => setAlloc((await api(`/api/tasks/${t.id}`)).result), 1200);
    } catch (e) { setErr((e as Error).message); }
  };

  return (
    <>
      <PageHeader kicker="Financial command center" title="Profitability, forecasts & capital">
        <select value={days} onChange={(e) => setDays(Number(e.target.value))} aria-label="Period (days)">{[7, 30, 90, 365].map((d) => <option key={d} value={d}>last {d} days</option>)}</select>
      </PageHeader>
      <ErrorBanner error={err || sum.error} />
      <LedgerEntryForm onSaved={() => { sum.reload(); fc.reload(); }} />
      {s && (
        <>
          {s.contains_demo_data && <div className="mb-4 rounded-md border border-violet-dim bg-violet/5 px-3 py-2 text-[12.5px] text-ink-2">Includes <b className="text-violet">synthetic demo</b> ledger entries.</div>}
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-8">
            <Stat label="Revenue" value={sek(s.revenue)} />
            <Stat label="Gross profit" value={sek(s.gross_profit)} />
            <Stat label="Contribution" value={sek(s.contribution_margin)} />
            <Stat label="Net profit" value={sek(s.net_profit)} accent />
            <Stat label="Ad spend" value={sek(s.ad_spend)} sub={`ROAS ${fmt(s.roas, 2)}`} />
            <Stat label="Refunds" value={sek(s.refunds)} />
            <Stat label="Chargebacks" value={sek(s.chargebacks)} />
            <Stat label="Tax recorded" value={sek(s.tax)} />
          </div>
          <div className="mt-4 grid grid-cols-1 gap-4 xl:grid-cols-3">
            <Card title="Daily revenue & profit" className="xl:col-span-2">
              {s.daily.length ? <RevenueProfitChart data={s.daily} /> : <Empty title="No ledger entries in range" />}
            </Card>
            <Card title="Forecast (OLS trend, ~80% band)">
              {fc.data?.available ? (
                <Table head={["Horizon", "Revenue", "Profit (range)"]}>
                  {Object.entries(fc.data.horizons).map(([h, v]: any) => (
                    <tr key={h}><td>{h} days</td><td className="num">{sek(v.revenue.expected)}</td>
                      <td className="num">{sek(v.profit.expected)} <span className="text-[11px] text-ink-3">({sek(v.profit.low)} – {sek(v.profit.high)})</span></td></tr>
                  ))}
                </Table>
              ) : <Empty title="Forecast unavailable">{fc.data?.reason}</Empty>}
            </Card>
          </div>
          <div className="mt-4 grid grid-cols-1 gap-4 xl:grid-cols-3">
            <Card title="Profit by product">
              <Table head={["Product", "Profit"]}>{Object.entries(s.profit_by_product).map(([k, v]: any) => <tr key={k}><td>{names.get(k) ?? `#${k}`}</td><td className="num">{sek(v)}</td></tr>)}</Table>
            </Card>
            <Card title="Profit by channel">
              <Table head={["Channel", "Profit"]}>{Object.entries(s.profit_by_channel).map(([k, v]: any) => <tr key={k}><td>{k}</td><td className="num">{sek(v)}</td></tr>)}</Table>
            </Card>
            <Card title="Capital allocation (recommendation only)">
              <div className="flex items-end gap-2">
                <Field label="Available capital (SEK)"><input type="number" value={capital} onChange={(e) => setCapital(e.target.value)} /></Field>
                <Button variant="primary" disabled={!capital} onClick={allocate}>Ask CFO</Button>
              </div>
              {alloc && (alloc.allocation ? (
                <div className="mt-3">
                  <Table head={["Bucket", "SEK"]}>{Object.entries(alloc.allocation).map(([k, v]: any) => <tr key={k}><td>{k.replaceAll("_", " ")}</td><td className="num">{sek(v)}</td></tr>)}</Table>
                  <p className="mt-2 text-[11.5px] text-ink-3">{alloc.note}</p>
                </div>
              ) : <Json value={alloc} />)}
            </Card>
          </div>
        </>
      )}
      <UnitEconomicsCalculator />
    </>
  );
}

function UnitEconomicsCalculator() {
  const [f, setF] = useState<Record<string, string>>({ retail_price_incl_vat: "449", unit_cost: "80", inbound_shipping: "30", packaging: "8", fulfillment: "0",
    import_duty_rate: "0.04", return_rate: "0.06", return_cost_per_return: "69", marketplace_fee_pct: "0", cac: "120", competitor_prices: "399,449,529" });
  const [res, setRes] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);
  const run = async () => {
    const body: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(f)) body[k] = k === "competitor_prices" ? v.split(",").map(Number).filter((n) => n > 0) : Number(v);
    try { setRes(await api("/api/tools/economics", { method: "POST", json: body })); setErr(null); } catch (e) { setErr((e as Error).message); }
  };
  const e = res?.economics;
  return (
    <Card title="Unit economics calculator · SEK, VAT 25%" className="mt-4">
      <ErrorBanner error={err} />
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-6">
        {Object.keys(f).map((k) => <Field key={k} label={k.replaceAll("_", " ")}><input value={f[k]} onChange={(ev) => setF({ ...f, [k]: ev.target.value })} /></Field>)}
      </div>
      <div className="mt-3"><Button variant="primary" onClick={run}>Calculate</Button></div>
      {e && (
        <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-2">
          <div className="grid grid-cols-2 gap-3 md:grid-cols-3">
            <Stat label="Net revenue" value={sek(e.net_revenue, 2)} sub={`VAT ${sek(e.vat, 2)}`} />
            <Stat label="Landed cost" value={sek(e.landed_cost, 2)} />
            <Stat label="Gross margin" value={pct(e.gross_margin, 1)} />
            <Stat label="Contribution before ads" value={sek(e.contribution_before_ads, 2)} />
            <Stat label="After CAC" value={sek(e.contribution_margin, 2)} accent sub={pct(e.contribution_margin_pct, 1)} />
            <Stat label="Break-even ROAS" value={fmt(e.break_even_roas, 2)} sub={`max CAC ${sek(e.break_even_cac)}`} />
          </div>
          {res.pricing?.scenarios && (
            <Table head={["Scenario", "Price", "Contribution", "Margin"]}>
              {Object.entries(res.pricing.scenarios).map(([k, s]: any) => (
                <tr key={k} title={s.rationale}><td>{k}</td><td className="num">{sek(s.price)}</td><td className="num">{sek(s.contribution_margin)}</td><td className="num">{pct(s.contribution_margin_pct)}</td></tr>
              ))}
            </Table>
          )}
        </div>
      )}
    </Card>
  );
}

const KINDS = ["revenue", "cogs", "shipping", "fees", "ad_spend", "refund", "chargeback", "opex", "tax"];

/** Real numbers in: one entry at a time here, or many at once as CSV/JSON (Opportunity database → Import). Amounts are
 *  positive; the kind decides the sign. Every entry is audited. */
function LedgerEntryForm({ onSaved }: { onSaved: () => void }) {
  const [open, setOpen] = useState(false);
  const [f, setF] = useState({ kind: "revenue", amount: "", occurred_at: new Date().toISOString().slice(0, 10), channel: "direct", reference: "", product_id: "" });
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const amount = Number(f.amount);
  const save = async () => {
    setBusy(true); setMsg(null);
    try {
      const r = await api<any>("/api/finance/ledger", { method: "POST", json: { kind: f.kind, amount, occurred_at: new Date(f.occurred_at).toISOString(),
        channel: f.channel || "direct", reference: f.reference, product_id: f.product_id ? Number(f.product_id) : null } });
      setMsg({ ok: true, text: `Recorded ${f.kind} ${sek(amount)} as entry #${r.id}.` }); setF({ ...f, amount: "", reference: "" }); onSaved();
    } catch (e) { setMsg({ ok: false, text: (e as Error).message }); } finally { setBusy(false); }
  };
  return (
    <div className="mb-4">
      <div className="flex flex-wrap items-center gap-2">
        <Button onClick={() => setOpen((o) => !o)}>{open ? "Close" : "Record an entry"}</Button>
        <Link className="text-[12.5px] text-violet hover:underline" href="/lab?import=ledger">Import many (CSV / JSON) →</Link>
      </div>
      {open && (
        <Card title="Record a ledger entry" className="mt-3">
          <div className="grid grid-cols-2 gap-3 md:grid-cols-6">
            <Field label="Kind"><select value={f.kind} onChange={(e) => setF({ ...f, kind: e.target.value })}>{KINDS.map((k) => <option key={k}>{k}</option>)}</select></Field>
            <Field label="Amount (SEK, positive)"><input inputMode="decimal" value={f.amount} onChange={(e) => setF({ ...f, amount: e.target.value })} /></Field>
            <Field label="Date"><input type="date" value={f.occurred_at} onChange={(e) => setF({ ...f, occurred_at: e.target.value })} /></Field>
            <Field label="Channel"><input value={f.channel} onChange={(e) => setF({ ...f, channel: e.target.value })} /></Field>
            <Field label="Product id (optional)"><input inputMode="numeric" value={f.product_id} onChange={(e) => setF({ ...f, product_id: e.target.value.replace(/\D/g, "") })} /></Field>
            <Field label="Reference"><input value={f.reference} onChange={(e) => setF({ ...f, reference: e.target.value })} placeholder="order / invoice no." /></Field>
          </div>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <Button variant="primary" busy={busy} disabled={!(amount >= 0) || f.amount === "" || !f.occurred_at} onClick={save}>Save entry</Button>
            {msg && <span role="status" className={`text-[12.5px] ${msg.ok ? "text-good" : "text-[#f08a8a]"}`}>{msg.text}</span>}
          </div>
        </Card>
      )}
    </div>
  );
}
