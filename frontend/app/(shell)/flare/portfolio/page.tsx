"use client";
import { useState } from "react";
import { Swatches } from "@/components/flare";
import { Button, Card, DemoBadge, Empty, ErrorBanner, Field, PageHeader, StatusBadge, Table } from "@/components/ui";
import { api, pct, sek } from "@/lib/api";
import { label } from "@/lib/flare";
import { useApi, useRefreshOn } from "@/lib/hooks";

export default function BrandPortfolio() {
  const data = useApi<any>("/api/flare/brands");
  useRefreshOn(["approval", "task"], data.reload);
  const [err, setErr] = useState<string | null>(null);
  const [tm, setTm] = useState<Record<number, string>>({});
  const act = async (fn: () => Promise<any>) => { try { await fn(); data.reload(); setErr(null); } catch (e) { setErr((e as Error).message); } };
  const brands = data.data?.brands ?? [];
  return (
    <>
      <PageHeader kicker="Rocky Flare · brand portfolio" title="Independent brands, one operating system" />
      <ErrorBanner error={err || data.error} />
      <p className="mb-4 max-w-3xl text-[13px] text-ink-3">Brands come from approved concepts. New brands that overlap an existing one are blocked unless justified — products that belong together stay together. Going live needs a cleared trademark search (recorded by an admin) and a LEVEL 4 approval.</p>
      <Card title="Brand comparison" pad={false}>
        {brands.length ? (
          <Table head={["Brand", "Status", "DNA", "Products", "Revenue", "Contribution", "Growth 30d", "Conversion", "Marketing cost", "Retention", "Recognition", "Complexity", "Trademark", ""]}>
            {brands.map((b: any) => (
              <tr key={b.brand_id} className="align-top">
                <td className="font-medium">{b.name}<DemoBadge show={b.demo_data} /><div className="max-w-56 text-[11px] text-ink-3">{b.audience}</div></td>
                <td><StatusBadge status={b.status} /></td>
                <td><Swatches colors={b.genre_dna?.direction?.color_palette ?? []} size={12} /><div className="text-[11px] text-ink-3">{(b.genre_dna?.genres ?? []).map(label).join(" × ")}</div></td>
                <td className="num">{b.products}</td><td className="num">{sek(b.revenue)}</td><td className="num">{sek(b.contribution)}</td>
                <td className="num">{pct(b.growth_30d)}</td><td className="num">{pct(b.conversion_rate, 1)}</td><td className="num">{sek(b.marketing_cost)}</td>
                <td className="num" title={b.retention_note ?? ""}>{b.retention_repeat_rate == null ? "n/a" : pct(b.retention_repeat_rate)}</td>
                <td className="num" title={b.recognition_note ?? ""}>{b.recognition_branded_search ?? "n/a"}</td>
                <td className="num">{b.operational_complexity}</td>
                <td><StatusBadge status={b.trademark_status === "clear" ? "approved" : b.trademark_status === "conflict" ? "blocked" : "pending"} /></td>
                <td className="space-y-1">
                  {b.trademark_status !== "clear" && (
                    <div className="flex flex-col gap-1">
                      <input placeholder="search evidence (registry, date)" value={tm[b.brand_id] ?? ""} onChange={(e) => setTm({ ...tm, [b.brand_id]: e.target.value })} className="w-52" />
                      <Button onClick={() => act(() => api(`/api/flare/brands/${b.brand_id}`, { method: "PATCH", json: { trademark_status: "clear", trademark_note: tm[b.brand_id] } }))}>Record clear (admin)</Button>
                    </div>
                  )}
                  {b.trademark_status === "clear" && b.status !== "live" && <>
                    <Button onClick={() => act(() => api(`/api/flare/brands/${b.brand_id}/request-launch`, { method: "POST" }))}>Request launch</Button>
                    <Button variant="primary" onClick={() => act(() => api(`/api/flare/brands/${b.brand_id}/activate`, { method: "POST" }))}>Activate</Button>
                  </>}
                </td>
              </tr>
            ))}
          </Table>
        ) : <div className="p-4"><Empty title="No brands yet">Approve a concept in the Brand Laboratory, then create a brand from it.</Empty></div>}
      </Card>
      <Card title="Extension opportunities" className="mt-4">
        {data.data?.extensions?.length ? <ul className="space-y-1.5 text-[13px]">{data.data.extensions.map((x: any, i: number) => <li key={i}><b className="text-ink-2">{label(x.type)}</b> · {x.brand}{x.product ? ` ← ${x.product}` : ""}: <span className="text-ink-3">{x.why}</span></li>)}</ul>
          : <Empty title="No extensions detected">Extensions appear when a brand is contribution-positive and related unbranded products exist.</Empty>}
      </Card>
      <AssignProduct brands={brands} onDone={data.reload} onError={setErr} />
    </>
  );
}

function AssignProduct({ brands, onDone, onError }: { brands: any[]; onDone: () => void; onError: (e: string) => void }) {
  const prods = useApi<any[]>("/api/products");
  const [b, setB] = useState(""); const [p, setP] = useState("");
  if (!brands.length) return null;
  return (
    <Card title="Add a product to an existing brand" className="mt-4">
      <div className="flex flex-wrap items-end gap-2">
        <Field label="Brand"><select value={b} onChange={(e) => setB(e.target.value)}><option value="">…</option>{brands.map((x) => <option key={x.brand_id} value={x.brand_id}>{x.name}</option>)}</select></Field>
        <Field label="Product"><select value={p} onChange={(e) => setP(e.target.value)}><option value="">…</option>{(prods.data ?? []).map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}</select></Field>
        <Button disabled={!b || !p} onClick={async () => { try { await api(`/api/flare/brands/${b}/products/${p}`, { method: "POST" }); onDone(); } catch (e) { onError((e as Error).message); } }}>Assign</Button>
      </div>
    </Card>
  );
}
