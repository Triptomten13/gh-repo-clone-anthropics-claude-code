"use client";
import { Activity, Archive, Beaker, Bot, Briefcase, Compass, Dna, FlaskConical, Gauge, GitFork, Landmark, Lightbulb, Megaphone, MessagesSquare, Palette, Power, Radar, Settings, ShieldCheck, Sparkles, UserCog } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";
import { api, getToken, setToken } from "@/lib/api";
import { useApi, useLiveEvents } from "@/lib/hooks";

type NavItem = { href: string; label: string; icon: typeof Gauge };
const GROUPS: { title: string; tone: string; items: NavItem[] }[] = [];
const NAV: NavItem[] = [
  { href: "/", label: "Executive Overview", icon: Gauge },
  { href: "/radar", label: "Market Radar", icon: Radar },
  { href: "/lab", label: "Product Laboratory", icon: FlaskConical },
  { href: "/portfolio", label: "Business Portfolio", icon: Briefcase },
  { href: "/agents", label: "Agent Control Room", icon: Bot },
  { href: "/finance", label: "Financial Command", icon: Landmark },
  { href: "/experiments", label: "Experiment Lab", icon: Beaker },
  { href: "/approvals", label: "Approval Center", icon: ShieldCheck },
  { href: "/archive", label: "Intelligence Archive", icon: Archive },
  { href: "/settings", label: "Systems & Integrations", icon: Settings },
];
const FLARE: NavItem[] = [
  { href: "/flare", label: "Creative Intelligence", icon: Sparkles },
  { href: "/flare/brands", label: "Brand Laboratory", icon: Palette },
  { href: "/flare/mutations", label: "Mutation Lab", icon: Dna },
  { href: "/flare/campaigns", label: "Campaign Studio", icon: Megaphone },
  { href: "/flare/portfolio", label: "Brand Portfolio", icon: GitFork },
  { href: "/flare/sideways", label: "Think Sideways", icon: Lightbulb },
  { href: "/flare/personas", label: "Personalities", icon: UserCog },
  { href: "/flare/collab", label: "Collaboration Log", icon: MessagesSquare },
];
const FIELD: NavItem[] = [{ href: "/field", label: "Field Operations", icon: Compass }];
GROUPS.push({ title: "Command", tone: "text-ink-3", items: NAV }, { title: "Rocky Flare", tone: "text-ember", items: FLARE },
  { title: "Field Ops", tone: "text-gold", items: FIELD });

export function RockyMark({ size = 28 }: { size?: number }) {
  // Original mark: a faceted granite peak with an ember summit line.
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden>
      <polygon points="2,27 12,9 17,17 21,12 30,27" fill="#2e2d2a" stroke="#5a5852" strokeWidth="1" />
      <polygon points="12,9 17,17 14,27 2,27" fill="#3d3c38" />
      <polyline points="9,14.5 12,9 15,14" fill="none" stroke="#f2a93b" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
      <line x1="2" y1="27" x2="30" y2="27" stroke="#f2a93b" strokeWidth="1" opacity=".6" />
    </svg>
  );
}

type Status = { kill_switch: { engaged?: boolean }; llm_provider: string; cost_today_usd: number; daily_cost_limit_usd: number };

export function Shell({ children }: { children: ReactNode }) {
  const path = usePathname();
  const router = useRouter();
  const [ready, setReady] = useState(false);
  useEffect(() => {
    if (!getToken()) router.replace("/login");
    else setReady(true);
  }, [router]);
  const status = useApi<Status>(ready ? "/api/system/status" : null);
  const approvals = useApi<any[]>(ready ? "/api/approvals?status=pending" : null);
  const { connected } = useLiveEvents((e) => {
    if (e.type === "kill_switch" || e.type === "task") status.reload();
    if (e.type === "approval") approvals.reload();
  });
  if (!ready) return null;
  const engaged = !!status.data?.kill_switch?.engaged;

  return (
    <div className="flex min-h-screen">
      <aside className="sticky top-0 hidden h-screen w-60 shrink-0 flex-col border-r border-line bg-[#121211]/90 md:flex">
        <div className="flex items-center gap-2.5 px-5 pb-3 pt-5">
          <RockyMark />
          <div>
            <div className="font-mono text-[15px] font-bold tracking-[0.32em]">ROCKY</div>
            <div className="font-mono text-[9.5px] uppercase tracking-[0.18em] text-ink-3">Commerce Intelligence HQ</div>
          </div>
        </div>
        <div className="scan-line mx-5 mb-3 opacity-50" />
        <nav className="flex-1 space-y-0.5 overflow-y-auto px-2 pb-3">
          {GROUPS.map((g) => (
          <div key={g.title} className="mb-2">
          <div className={`px-3 pb-1 pt-2 font-mono text-[9.5px] uppercase tracking-[0.22em] ${g.tone}`}>{g.title}</div>
          {g.items.map(({ href, label, icon: Icon }) => {
            const active = href === "/" ? path === "/" : href === "/flare" ? path === "/flare" : path.startsWith(href);
            return (
              <Link key={href} href={href}
                className={`flex items-center gap-2.5 rounded-md px-3 py-1.5 text-[13px] transition ${active ? "bg-surface-2 text-ink" : "text-ink-3 hover:bg-surface hover:text-ink-2"}`}>
                <Icon size={15} className={active ? "text-ember" : ""} />
                <span className="flex-1">{label}</span>
                {href === "/approvals" && (approvals.data?.length ?? 0) > 0 && (
                  <span className="num rounded bg-ember px-1.5 text-[11px] font-semibold text-black">{approvals.data!.length}</span>
                )}
              </Link>
            );
          })}
          </div>
          ))}
        </nav>
        <div className="border-t border-line px-4 py-3 text-[11px] text-ink-3">
          <div className="flex items-center gap-1.5">
            <Activity size={12} className={connected ? "text-good" : "text-ink-3"} />
            {connected ? "Live feed connected" : "Live feed offline"}
          </div>
          <button className="mt-2 text-ink-3 underline-offset-2 hover:text-ink-2 hover:underline"
            onClick={() => { setToken(null); router.replace("/login"); }}>Sign out</button>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className={`sticky top-0 z-10 flex flex-wrap items-center gap-x-5 gap-y-1 border-b px-6 py-2.5 text-[12px] backdrop-blur ${engaged ? "border-critical/60 bg-critical/15" : "border-line bg-bg/80"}`}>
          <span className="font-mono font-bold tracking-[0.3em] md:hidden">ROCKY</span>
          <span className="text-ink-3">AI: <span className={status.data?.llm_provider === "none" ? "text-warning" : "text-ink-2"}>
            {status.data?.llm_provider === "none" ? "not configured" : status.data?.llm_provider ?? "…"}</span></span>
          <span className="num text-ink-3">AI spend today: <span className="text-ink-2">${status.data?.cost_today_usd?.toFixed(2) ?? "…"}</span> / ${status.data?.daily_cost_limit_usd ?? "…"}</span>
          <span className="flex-1" />
          <KillSwitch engaged={engaged} onChange={status.reload} />
        </header>
        <main className="mx-auto w-full max-w-[1500px] flex-1 px-4 py-6 md:px-8">{children}</main>
      </div>
    </div>
  );
}

function KillSwitch({ engaged, onChange }: { engaged: boolean; onChange: () => void }) {
  const [busy, setBusy] = useState(false);
  const toggle = async () => {
    const reason = engaged ? "" : prompt("Emergency stop: reason?") ?? "";
    if (!engaged && !reason) return;
    setBusy(true);
    try { await api("/api/system/kill-switch", { method: "POST", json: { engaged: !engaged, reason } }); onChange(); }
    catch (e) { alert((e as Error).message); }
    finally { setBusy(false); }
  };
  return (
    <button onClick={toggle} disabled={busy}
      className={`inline-flex items-center gap-1.5 rounded-md border px-2.5 py-1 font-mono text-[11px] uppercase tracking-wider ${engaged ? "border-critical bg-critical text-white" : "border-critical/50 text-[#f08a8a] hover:bg-critical/15"}`}>
      <Power size={12} />{engaged ? "Halted · release" : "Emergency stop"}
    </button>
  );
}
