"use client";
/** Where every setting lives and what it is set to now. Each setting has ONE home (its own page enforces and audits it);
 *  this map only reads current values and links there — it never duplicates a control. */
import Link from "next/link";
import type { ReactNode } from "react";
import { Card } from "@/components/ui";
import { useApi } from "@/lib/hooks";

type Row = { group: string; setting: string; value: ReactNode; href?: string; where: string };

export function SettingsMap() {
  const d = useApi<any>("/api/daemon/settings");
  const sys = useApi<any>("/api/system/status");
  const dep = useApi<any>("/api/deployment");
  const pol = useApi<any>("/api/policies");
  const bud = useApi<any[]>("/api/budgets");
  const v = (x: unknown, fallback = "—") => (x === undefined || x === null ? fallback : String(x));
  const rows: Row[] = [
    { group: "AI", setting: "Offline mode / external providers", value: d.data ? `${d.data.offline_mode ? "offline" : "online"} · external ${d.data.external_allowed ? "allowed" : "off"}` : d.error ? "—" : "…", href: "/daemon#status", where: "DAEMON CORE → Status" },
    { group: "AI", setting: "Routing profile", value: d.data ? v(d.data.profile) : d.error ? "—" : "…", href: "/daemon#status", where: "DAEMON CORE → Status" },
    { group: "AI", setting: "Provider keys", value: "encrypted on the server; never shown", href: "/daemon#providers", where: "DAEMON CORE → Providers & keys" },
    { group: "AI", setting: "Models, slots, local library", value: "", href: "/daemon#models", where: "DAEMON CORE → Models" },
    { group: "Resource budgets", setting: "Daily AI spend limit", value: sys.data ? `$${sys.data.daily_cost_limit_usd}` : "…", where: "server environment (DAILY_COST_LIMIT_USD)" },
    { group: "Resource budgets", setting: "Hard limits per user / agent / workflow", value: bud.data ? `${bud.data.filter((b) => b.enabled).length} active` : bud.error ? "—" : "…", href: "/governance#budgets", where: "Governance → Budgets" },
    { group: "Agent behaviour", setting: "Permission level, suspension, token budget", value: "", href: "/agents", where: "Agents" },
    { group: "Agent behaviour", setting: "Emergency stop", value: sys.data ? (sys.data.kill_switch?.engaged ? "ENGAGED" : "released") : "…", where: "top bar → Emergency stop" },
    { group: "Workflows", setting: "Scheduler", value: sys.data ? (sys.data.scheduler_enabled ? "enabled" : "disabled") : "…", where: "this page → Runtime" },
    { group: "Security", setting: "Policy rules", value: pol.data ? `${pol.data.rules?.length ?? 0} rules · version ${String(pol.data.version ?? "").slice(0, 8)}` : pol.error ? "—" : "…", href: "/governance#policies", where: "Governance → Policies" },
    { group: "Security", setting: "Tool grants", value: "", href: "/governance#tools", where: "Governance → Tool security" },
    { group: "Security", setting: "Release gates", value: "", href: "/governance#gates", where: "Governance → Evaluation gates" },
    { group: "Permissions", setting: "Users and roles", value: "", where: "this page → Users & access" },
    { group: "Knowledge", setting: "Collections and document access", value: "", href: "/knowledge#documents", where: "The Archive → Documents" },
    { group: "Network / deployment", setting: "Deployment profile and egress", value: dep.data ? v(dep.data.deployment?.profile) : dep.error ? "—" : "…", href: "/governance#deployment", where: "Governance → Deployment & egress" },
    { group: "Monitoring", setting: "Audit retention", value: "minimum age from AUDIT_MIN_RETENTION_DAYS", href: "/governance#audit", where: "Governance → Audit & compliance" },
    { group: "Monitoring", setting: "Research monitors", value: "", href: "/research", where: "Research & Monitoring" },
    { group: "Appearance", setting: "Theme", value: "dark only — no setting", where: "—" },
    { group: "Notifications", setting: "Alerts", value: "in the app only (Needs attention, live feed); e-mail / push not implemented", href: "/", where: "Command center" },
  ];
  return (
    <Card title="Where every setting lives" className="mb-4" pad={false}>
      <div className="overflow-x-auto">
        <table className="w-full text-[12.5px]" aria-label="Settings and where they are changed">
          <thead><tr className="text-left font-mono text-[10px] uppercase tracking-[0.14em] text-ink-3"><th className="px-4 py-2">Area</th><th className="px-4 py-2">Setting</th><th className="px-4 py-2">Now</th><th className="px-4 py-2">Changed in</th></tr></thead>
          <tbody className="divide-y divide-line">{rows.map((r) => (
            <tr key={r.setting}><td className="px-4 py-2 text-ink-3">{r.group}</td><td className="px-4 py-2">{r.setting}</td><td className="px-4 py-2 text-ink-2">{r.value || "—"}</td>
              <td className="px-4 py-2">{r.href ? <Link className="text-violet underline underline-offset-2" href={r.href}>{r.where}</Link> : <span className="text-ink-3">{r.where}</span>}</td></tr>))}
          </tbody>
        </table>
      </div>
      <p className="px-4 py-2 text-[11.5px] text-ink-3">Each setting has one home that enforces and audits it; this table only shows the current value. &quot;—&quot; means the value is not readable with your permissions.</p>
    </Card>
  );
}
