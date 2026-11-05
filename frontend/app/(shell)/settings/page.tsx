"use client";
import { useState } from "react";
import { Button, Card, ErrorBanner, PageHeader, StatusBadge, Table } from "@/components/ui";
import { api } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { PasswordCard, UsersCard } from "@/components/users";

export default function SettingsPage() {
  const integ = useApi<any[]>("/api/integrations");
  const status = useApi<any>("/api/system/status");
  const [err, setErr] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const call = async (path: string, method: string, label: string) => {
    try { const r = await api(path, { method }); setMsg(`${label}: ${JSON.stringify(r)}`); setErr(null); status.reload(); } catch (e) { setErr((e as Error).message); }
  };
  const groups = ["research", "commerce", "payments", "fulfillment", "marketing"];
  return (
    <>
      <PageHeader kicker="Systems & integrations" title="Configuration status" />
      <ErrorBanner error={err} />
      {msg && <div className="mb-4 rounded-md border border-line bg-surface px-3 py-2 font-mono text-[12px] text-ink-2">{msg}</div>}
      <div className="grid gap-4 xl:grid-cols-3">
        <Card title="Runtime">
          {status.data && (
            <dl className="grid grid-cols-2 gap-y-1.5 text-[13px]">
              <dt className="text-ink-3">AI provider</dt><dd>{status.data.llm_provider === "none" ? <StatusBadge status="missing_credentials" /> : status.data.llm_provider}</dd>
              <dt className="text-ink-3">External tier models</dt><dd className="font-mono text-[11.5px]">{Object.entries(status.data.models).map(([k, v]) => <div key={k}>{k}: {v as string}</div>)}</dd>
              <dt className="text-ink-3">Daily AI cost limit</dt><dd className="num">${status.data.daily_cost_limit_usd}</dd>
              <dt className="text-ink-3">Max delegation depth</dt><dd className="num">{status.data.max_task_depth}</dd>
              <dt className="text-ink-3">Scheduler</dt><dd>{status.data.scheduler_enabled ? "enabled" : "disabled (SCHEDULER_ENABLED)"}</dd>
              <dt className="text-ink-3">Last runs</dt><dd className="font-mono text-[11px]">{Object.entries(status.data.scheduler_state).map(([k, v]) => <div key={k}>{k}: {(v as string).slice(0, 16)}</div>)}</dd>
              <dt className="text-ink-3">Database</dt><dd>{status.data.database}</dd>
            </dl>
          )}
          <div className="mt-4 flex flex-wrap gap-2 border-t border-line pt-3">
            <Button onClick={() => call("/api/scheduler/tick", "POST", "Scheduler tick")}>Run scheduler tick now</Button>
          </div>
        </Card>
        <Card title="Demo dataset" className="xl:col-span-2">
          <p className="mb-3 text-[13px] text-ink-2">Loads synthetic, clearly badged sample products, trends and ledger entries so you can explore the command center before any connector is configured. It is not market data and must be removed before real use.</p>
          <div className="flex gap-2"><Button onClick={() => call("/api/demo", "POST", "Demo loaded")}>Load demo data</Button><Button variant="danger" onClick={() => call("/api/demo", "DELETE", "Demo removed")}>Remove demo data</Button></div>
        </Card>
      </div>
      <div className="mt-4 grid gap-4 xl:grid-cols-3">
        <div className="xl:col-span-2"><UsersCard /></div>
        <PasswordCard />
      </div>
      {groups.map((g) => {
        const rows = (integ.data ?? []).filter((i) => i.kind === g);
        if (!rows.length) return null;
        return (
          <Card key={g} title={`${g} integrations`} className="mt-4" pad={false}>
            <Table head={["Platform", "State", "Required environment", "Access notes", "Docs"]}>
              {rows.map((i) => (
                <tr key={i.id}>
                  <td className="font-medium">{i.name}</td><td><StatusBadge status={i.state} /></td>
                  <td className="font-mono text-[11.5px]">{i.required_env.map((e: string) => <div key={e} className={i.missing_env.includes(e) ? "text-warning" : "text-ink-2"}>{e}</div>)}</td>
                  <td className="max-w-md text-[12px] text-ink-3">{i.access_notes}</td>
                  <td>{i.docs_url && <a className="text-[12px] text-violet hover:underline" href={i.docs_url} target="_blank" rel="noreferrer">docs ↗</a>}</td>
                </tr>
              ))}
            </Table>
          </Card>
        );
      })}
    </>
  );
}
