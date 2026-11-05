"use client";
import Link from "next/link";
import { Card, Empty, ErrorBanner, PageHeader, StatusBadge, Table } from "@/components/ui";
import { ago } from "@/lib/api";
import { useApi, useRefreshOn } from "@/lib/hooks";

export default function PortfolioPage() {
  const opps = useApi<any[]>("/api/opportunities");
  const prods = useApi<any[]>("/api/products?status=launched");
  useRefreshOn(["task"], opps.reload);
  const byProduct = new Map<number, any>();
  for (const o of opps.data ?? []) if (!byProduct.has(o.product_id)) byProduct.set(o.product_id, o);
  const latest = [...byProduct.values()];
  const modelCount: Record<string, number> = {};
  latest.forEach((o) => o.business_models.forEach((m: any) => { modelCount[m.model] = (modelCount[m.model] ?? 0) + 1; }));

  return (
    <>
      <PageHeader kicker="Business portfolio" title="Opportunities, models & businesses" />
      <ErrorBanner error={opps.error} />
      <div className="grid gap-4 xl:grid-cols-3">
        <Card title="Live businesses">
          {prods.data?.length ? prods.data.map((p) => <div key={p.id} className="py-1 text-[13px]">{p.name}</div>) :
            <Empty title="No live businesses yet">A product becomes live only after a human approves its compliance review and launch request.</Empty>}
        </Card>
        <Card title="Business models across opportunities" className="xl:col-span-2">
          {Object.keys(modelCount).length ? (
            <div className="flex flex-wrap gap-2">
              {Object.entries(modelCount).sort((a, b) => b[1] - a[1]).map(([m, n]) => (
                <span key={m} className="rounded-md border border-line-strong px-2.5 py-1 text-[12.5px]">{m.replaceAll("_", " ")} <span className="num ml-1 text-violet">×{n}</span></span>
              ))}
            </div>
          ) : <Empty title="No opportunities yet" />}
        </Card>
      </div>
      <Card title="Opportunity pipeline" className="mt-4" pad={false}>
        {latest.length ? (
          <Table head={["Opportunity", "Top 3 business models", "Concepts", "Standard price", "Status", "Created"]}>
            {latest.map((o) => (
              <tr key={o.id}>
                <td className="font-medium"><Link href={`/lab/${o.product_id}`} className="hover:text-violet">{o.product_name}</Link></td>
                <td className="text-ink-2">{o.business_models.map((m: any) => m.model.replaceAll("_", " ")).join(" · ")}</td>
                <td className="num">{o.transformations.length}</td>
                <td className="num">{o.pricing?.scenarios?.standard?.price ? `${o.pricing.scenarios.standard.price} kr` : "—"}</td>
                <td><StatusBadge status={o.status} /></td>
                <td className="text-ink-3">{ago(o.created_at)}</td>
              </tr>
            ))}
          </Table>
        ) : <div className="p-4"><Empty title="Pipeline is empty">Evaluate products in the laboratory to generate opportunities.</Empty></div>}
      </Card>
    </>
  );
}
