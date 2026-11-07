"use client";
import { Bot, BookOpen, Cpu, Gauge, Library, ScrollText, ShieldCheck, Sparkles } from "lucide-react";
import Link from "next/link";
import { FeatureStatus, PublicFrame, useEnter, usePublicStatus } from "@/components/public";
import { Button, ErrorBanner, StatusBadge } from "@/components/ui";
import { useIdentity } from "@/lib/identity";

const EXPLORE = [
  { href: "/demo", label: "Open Demo", icon: Sparkles, text: "Run the approved sample workflows and see what each one proves.", demoOnly: true },
  { href: "/agents", label: "Agent Directory", icon: Bot, text: "Every agent, its division, permission level, tasks and policy." },
  { href: "/chamber", label: "Workflow Center", icon: Gauge, text: "G-sus turns an objective into a plan, delegates it and verifies the results." },
  { href: "/knowledge", label: "Knowledge Vault", icon: Library, text: "Search with citations; documents you may not read never reach the results." },
  { href: "/daemon", label: "Model Intelligence", icon: Cpu, text: "Local models, routing policy, offline mode, costs and benchmarks." },
  { href: "/governance", label: "Governance & Audit", icon: ShieldCheck, text: "Policies, tool grants, execution traces, release gates and the audit chain." },
];

const HOW = [
  ["An organisation, not a chatbot", "G-sus is the head orchestrator. It plans over capabilities that are actually registered, delegates the steps to specialised agents through one orchestrator, compares their results, reports contradictions and verifies before it answers."],
  ["Every action has a permission level", "Research and analysis run on their own; publishing, customer messages, purchases and budgets (levels 4–5) stop for a human approval that is bound to the exact action, expires, is used once and can never come from the person who asked."],
  ["Private AI first", "Models run locally (llama.cpp) where the hardware allows. Data classification decides which models may see retrieved text: restricted documents never leave this machine, and offline mode never falls back to an external service."],
  ["Governed and traceable", "Tools are deny-by-default per agent and operation, budgets are reserved before a call runs, every execution leaves a replayable trace, and the audit trail is a verifiable hash chain."],
];

const DOCS = [
  ["docs/CONTROL_PLANE.md", "architecture, policies, roles, routing, air-gap, implementation matrix"],
  ["docs/SECURITY.md", "permission levels, threat model, incident response, retention"],
  ["docs/PUBLIC_LAUNCH.md", "deployment, demo mode, environments, readiness matrix"],
  ["docs/AGENTS.md", "every agent, its permission level and outputs"],
  ["docs/TESTING.md", "every automated test layer and how to run it"],
];

export default function Welcome() {
  const identity = useIdentity();
  const st = usePublicStatus();
  const demoMode = st.data?.demo_mode ?? false;
  const { enter, busy, error } = useEnter(demoMode);
  return (
    <PublicFrame demoMode={st.data ? demoMode : null}>
      <section className="mb-10">
        <div className="mb-2 font-mono text-[11px] uppercase tracking-[0.22em] text-violet">{demoMode ? "Public demo" : "Governed AI agent platform"}</div>
        <h1 className="max-w-3xl font-serif text-[clamp(28px,5vw,44px)] font-semibold leading-tight">{identity.company_name}</h1>
        <p className="mt-3 max-w-2xl text-[15px] text-ink-2">
          G-SUS is the intelligence, Demonkoncernen the infrastructure, the Archive the memory, the agents the workforce — and
          the people stay in control. This is the real application{demoMode ? ", running on synthetic sample data in an isolated sandbox" : ""}.
        </p>
        <ErrorBanner error={error || (st.error ? `Status unavailable: ${st.error}` : null)} />
        <div className="mt-5 flex flex-wrap gap-2">
          {demoMode ? <Button variant="primary" busy={busy} onClick={() => enter("/demo")}>Open the demo — no account needed</Button>
            : <Link href="/login" className="inline-flex min-h-9 items-center rounded-md bg-violet px-4 text-[13px] font-semibold text-black">Sign in</Link>}
          <Button onClick={() => enter("/agents")}>Explore the platform</Button>
          <Link href="/status" className="inline-flex min-h-9 items-center rounded-md border border-line px-3 text-[13px] text-ink-2 hover:border-line-strong">System status</Link>
        </div>
        {demoMode && <p className="mt-3 text-[12.5px] text-ink-3">A demo session is a temporary visitor account: it can read sample data and run the approved sample workflows. It cannot approve, use tools, upload, change settings or reach anything outside this sandbox.</p>}
      </section>

      <section aria-labelledby="explore" className="mb-10">
        <h2 id="explore" className="mb-3 font-serif text-[22px] font-semibold">Explore</h2>
        <ul className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {EXPLORE.filter((e) => !e.demoOnly || demoMode).map(({ href, label, icon: Icon, text }) => (
            <li key={href}>
              <button onClick={() => enter(href)} disabled={busy} className="flex h-full w-full flex-col items-start gap-1.5 rounded-lg border border-line bg-surface p-4 text-left hover:border-line-strong">
                <span className="flex items-center gap-2 font-medium text-ink"><Icon size={16} className="text-violet" aria-hidden />{label}</span>
                <span className="text-[13px] text-ink-3">{text}</span>
              </button>
            </li>
          ))}
          <li>
            <Link href="/status" className="flex h-full flex-col items-start gap-1.5 rounded-lg border border-line bg-surface p-4 hover:border-line-strong">
              <span className="flex items-center gap-2 font-medium text-ink"><ScrollText size={16} className="text-cyan" aria-hidden />System Status</span>
              <span className="text-[13px] text-ink-3">Which components are operational, and which optional services are not configured here.</span>
            </Link>
          </li>
        </ul>
      </section>

      <section aria-labelledby="how" className="mb-10">
        <h2 id="how" className="mb-3 font-serif text-[22px] font-semibold">How it works</h2>
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
          {HOW.map(([t, d]) => <div key={t} className="rounded-lg border border-line bg-surface p-4"><h3 className="mb-1 font-medium">{t}</h3><p className="text-[13.5px] text-ink-2">{d}</p></div>)}
        </div>
      </section>

      <section aria-labelledby="works" className="mb-10">
        <h2 id="works" className="mb-1 font-serif text-[22px] font-semibold">What works on this server</h2>
        <p className="mb-3 text-[13px] text-ink-3">Reported by this server ({st.data ? <>overall <StatusBadge status={st.data.overall} /></> : "loading…"}). Nothing is listed as available that it cannot do.</p>
        {st.data && (
          <ul className="divide-y divide-line rounded-lg border border-line bg-surface">
            {st.data.features.map((f) => (
              <li key={f.name} className="flex flex-wrap items-center gap-x-3 gap-y-1 px-4 py-2.5 text-[13.5px]">
                <span className="min-w-0 flex-1">{f.name}{f.note && <span className="text-ink-3"> — {f.note}</span>}</span>
                <FeatureStatus status={f.status} />
              </li>
            ))}
          </ul>
        )}
      </section>

      <section id="docs" aria-labelledby="docs-h">
        <h2 id="docs-h" className="mb-3 flex items-center gap-2 font-serif text-[22px] font-semibold"><BookOpen size={18} className="text-gold" aria-hidden />Documentation</h2>
        <p className="mb-3 text-[13px] text-ink-3">In the project repository:</p>
        <ul className="space-y-1.5 text-[13.5px]">{DOCS.map(([f, d]) => <li key={f}><code className="font-mono text-[12.5px] text-cyan">{f}</code> <span className="text-ink-3">— {d}</span></li>)}</ul>
      </section>
    </PublicFrame>
  );
}
