"use client";
import { RefreshCw } from "lucide-react";
import { useEffect, useState } from "react";
import { PublicFrame, usePublicStatus } from "@/components/public";
import { Button, ErrorBanner, StatusBadge } from "@/components/ui";

// component states → the shared badge vocabulary (icon + label, never colour alone)
const BADGE: Record<string, string> = { operational: "operational", failed: "failed", paused: "paused", not_configured: "not_integrated", disabled: "disabled" };
const LABEL: Record<string, string> = { not_configured: "not configured", disabled: "disabled" };

export default function Status() {
  const st = usePublicStatus();
  const [checked, setChecked] = useState<Date | null>(null);
  useEffect(() => { if (st.data || st.error) setChecked(new Date()); }, [st.data, st.error]);
  const d = st.data;
  return (
    <PublicFrame demoMode={d ? d.demo_mode : null}>
      <div className="mb-6 flex flex-wrap items-end gap-3">
        <div className="min-w-0 flex-1">
          <div className="font-mono text-[11px] uppercase tracking-[0.22em] text-cyan">System status</div>
          <h1 className="font-serif text-[30px] font-semibold">{d ? (d.overall === "operational" ? "All core services operational" : d.overall === "degraded" ? "Degraded" : "Outage") : st.error ? "Server unreachable" : "Checking…"}</h1>
        </div>
        <Button onClick={() => st.reload()}><RefreshCw size={13} aria-hidden /> Check again</Button>
      </div>
      <ErrorBanner error={st.error ? `The backend did not answer: ${st.error}. The web server is up (you are reading this page); the API, database or agents may be down.` : null} />
      <ul className="mb-6 divide-y divide-line rounded-lg border border-line bg-surface" aria-label="Components">
        <li className="flex flex-wrap items-center gap-x-3 gap-y-1 px-4 py-3">
          <span className="min-w-0 flex-1"><span className="font-medium">Web application</span><span className="block text-[12.5px] text-ink-3">served this page</span></span>
          <StatusBadge status="operational" />
        </li>
        {d?.components.map((c) => (
          <li key={c.id} className="flex flex-wrap items-center gap-x-3 gap-y-1 px-4 py-3">
            <span className="min-w-0 flex-1">
              <span className="font-medium">{c.name}</span> <span className="font-mono text-[10px] uppercase tracking-wider text-ink-3">{c.kind === "core" ? "core" : "optional"}</span>
              {c.detail && <span className="block text-[12.5px] text-ink-3">{c.detail}</span>}
            </span>
            <span className="inline-flex items-center gap-1.5"><StatusBadge status={BADGE[c.status] ?? c.status} />{LABEL[c.status] && <span className="sr-only">{LABEL[c.status]}</span>}</span>
          </li>
        ))}
      </ul>
      {d && (
        <dl className="grid grid-cols-2 gap-x-6 gap-y-2 text-[13px] sm:grid-cols-4">
          <div><dt className="text-ink-3">Environment</dt><dd>{d.environment}</dd></div>
          <div><dt className="text-ink-3">Version</dt><dd className="num">{d.version} · {d.commit}</dd></div>
          <div><dt className="text-ink-3">Up for</dt><dd className="num">{Math.floor(d.uptime_s / 3600)} h {Math.floor((d.uptime_s % 3600) / 60)} min</dd></div>
          <div><dt className="text-ink-3">Last successful check</dt><dd className="num">{checked && !st.error ? checked.toLocaleTimeString() : "—"}</dd></div>
        </dl>
      )}
      <p className="mt-6 text-[12.5px] text-ink-3">Core components must work for the platform to run. Optional services (AI models, external providers, research) can be unconfigured or disabled on purpose — that is shown as such, not as a failure.</p>
    </PublicFrame>
  );
}
