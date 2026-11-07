"use client";
import { useState } from "react";
import { Button, Card, Empty, ErrorBanner, Field, Json, PageHeader, StatusBadge, Table } from "@/components/ui";
import { ago, api, sek } from "@/lib/api";
import { useApi, useRefreshOn } from "@/lib/hooks";

export default function ExperimentsPage() {
  const ex = useApi<any[]>("/api/experiments");
  useRefreshOn(["task", "approval"], ex.reload);
  const [err, setErr] = useState<string | null>(null);
  const [f, setF] = useState({ name: "", hypothesis: "", variant_a: "", variant_b: "", budget_sek: "0", min_roas: "2", kill_roas: "1", min_orders: "20", predicted_roas: "", predicted_cvr: "" });
  const [results, setResults] = useState<Record<number, string>>({});

  const create = async () => {
    const predicted: Record<string, number> = {};
    if (f.predicted_roas) predicted.roas = Number(f.predicted_roas);
    if (f.predicted_cvr) predicted.conversion_rate = Number(f.predicted_cvr);
    try {
      await api("/api/experiments", { method: "POST", json: { name: f.name, hypothesis: f.hypothesis, variant_a: f.variant_a, variant_b: f.variant_b,
        budget_sek: Number(f.budget_sek), predicted, success_metrics: { min_roas: Number(f.min_roas), kill_roas: Number(f.kill_roas), min_orders: Number(f.min_orders), min_contribution_margin: 0 } } });
      ex.reload();
    } catch (e) { setErr((e as Error).message); }
  };
  const start = async (id: number) => { try { await api(`/api/experiments/${id}/start`, { method: "POST" }); ex.reload(); } catch (e) { setErr((e as Error).message); } };
  const record = async (id: number) => {
    try { await api(`/api/experiments/${id}/results`, { method: "POST", json: JSON.parse(results[id] || "{}") }); ex.reload(); } catch (e) { setErr((e as Error).message); }
  };

  return (
    <>
      <PageHeader kicker="Experiment laboratory" title="Hypotheses, tests & decisions" />
      <ErrorBanner error={err || ex.error} />
      <Card title="Pre-register an experiment (metrics are fixed before results arrive)">
        <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
          <Field label="Name"><input value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></Field>
          <div className="col-span-2"><Field label="Hypothesis"><input className="w-full" value={f.hypothesis} onChange={(e) => setF({ ...f, hypothesis: e.target.value })} /></Field></div>
          <Field label="Variant A"><input value={f.variant_a} onChange={(e) => setF({ ...f, variant_a: e.target.value })} /></Field>
          <Field label="Variant B"><input value={f.variant_b} onChange={(e) => setF({ ...f, variant_b: e.target.value })} /></Field>
          {(["budget_sek", "min_roas", "kill_roas", "min_orders", "predicted_roas", "predicted_cvr"] as const).map((k) => (
            <Field key={k} label={k.replaceAll("_", " ")}><input type="number" step="any" value={f[k]} onChange={(e) => setF({ ...f, [k]: e.target.value })} /></Field>
          ))}
        </div>
        <div className="mt-3 flex items-center gap-3">
          <Button variant="primary" disabled={!f.name || !f.hypothesis} onClick={create}>Create</Button>
          <span className="text-[12px] text-ink-3">Any budget &gt; 0 creates a LEVEL 5 approval request before the experiment can start.</span>
        </div>
      </Card>
      <Card title="Experiments" className="mt-4" pad={false}>
        {ex.data?.length ? (
          <Table head={["Experiment", "Status", "Budget", "Success metrics", "Predicted", "Actual", "Decision", ""]}>
            {ex.data.map((e) => (
              <tr key={e.id} className="align-top">
                <td><div className="font-medium">{e.name}</div><div className="max-w-xs text-[12px] text-ink-3">{e.hypothesis}</div>{e.lessons && <div className="mt-1 max-w-xs text-[11.5px] text-ink-2">Lesson: {e.lessons}</div>}</td>
                <td><StatusBadge status={e.status} /></td><td className="num">{sek(e.budget_sek)}</td>
                <td className="text-[11.5px]"><Json value={e.success_metrics} /></td><td className="text-[11.5px]"><Json value={e.predicted} /></td>
                <td className="text-[11.5px]">{Object.keys(e.actual).length ? <Json value={e.actual} /> : "—"}</td>
                <td>{e.decision ? <StatusBadge status={e.decision} /> : "—"}</td>
                <td className="space-y-2">
                  {["draft", "pending_approval"].includes(e.status) && <Button onClick={() => start(e.id)}>Start</Button>}
                  {e.status === "running" && (
                    <div className="flex flex-col gap-1.5">
                      <textarea rows={3} className="w-56 font-mono text-[11px]" placeholder='{"orders":24,"roas":2.4,"contribution_margin":1200,"spend":1500}'
                        value={results[e.id] ?? ""} onChange={(ev) => setResults({ ...results, [e.id]: ev.target.value })} />
                      <Button onClick={() => record(e.id)}>Record results & evaluate</Button>
                    </div>
                  )}
                  <div className="text-[11px] text-ink-3">{ago(e.created_at)}</div>
                </td>
              </tr>
            ))}
          </Table>
        ) : <div className="p-4"><Empty title="No experiments yet">Every launch should start as a capped, pre-registered experiment.</Empty></div>}
      </Card>
    </>
  );
}
