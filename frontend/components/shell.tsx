"use client";
import { Activity, Archive, Beaker, Telescope, BookOpen, Bot, Briefcase, Building2, CloudOff, Compass, Cpu, Flame, Dna, FlaskConical, Gauge, GitFork, Home, Landmark, Library, Lightbulb, Megaphone, MessagesSquare, MoreHorizontal, PanelLeftClose, PanelLeftOpen, Palette, Power, Radar, Search, Settings, ShieldCheck, Sparkles, UserCog, WandSparkles, WifiOff, X } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { DialogProvider, useDialog } from "@/components/dialog";
import { api, getToken, setToken } from "@/lib/api";
import { useApi, useLiveEvents, type LiveStatus } from "@/lib/hooks";
import { useIdentity } from "@/lib/identity";

type NavItem = { href: string; label: string; icon: typeof Gauge };
const GSUS: NavItem[] = [
  { href: "/chamber", label: "G-sus Chamber", icon: Sparkles },
  { href: "/knowledge", label: "The Archive", icon: Library },
  { href: "/archivum", label: "Archivum", icon: BookOpen },
  { href: "/flare/collab", label: "The Council", icon: MessagesSquare },
];
const DEMON: NavItem[] = [
  { href: "/hq", label: "Demonkoncernen HQ", icon: Building2 },
  { href: "/control", label: "Control Center", icon: Gauge },
  { href: "/daemon", label: "DAEMON CORE", icon: Flame },
  { href: "/research", label: "Research & Monitoring", icon: Telescope },
  { href: "/ai", label: "AI Core", icon: Cpu },
  { href: "/agents", label: "Agent Registry", icon: Bot },
  { href: "/approvals", label: "Approval Center", icon: ShieldCheck },
  { href: "/archive", label: "Audit & Lessons", icon: Archive },
  { href: "/settings", label: "Systems & Integrations", icon: Settings },
];
const COMMERCE: NavItem[] = [
  { href: "/", label: "Executive Overview", icon: Gauge },
  { href: "/radar", label: "Market Radar", icon: Radar },
  { href: "/lab", label: "Product Laboratory", icon: FlaskConical },
  { href: "/portfolio", label: "Business Portfolio", icon: Briefcase },
  { href: "/finance", label: "Financial Command", icon: Landmark },
  { href: "/experiments", label: "Experiment Lab", icon: Beaker },
];
const FLARE: NavItem[] = [
  { href: "/flare", label: "Creative Intelligence", icon: WandSparkles },
  { href: "/flare/brands", label: "Brand Laboratory", icon: Palette },
  { href: "/flare/mutations", label: "Mutation Lab", icon: Dna },
  { href: "/flare/campaigns", label: "Campaign Studio", icon: Megaphone },
  { href: "/flare/portfolio", label: "Brand Portfolio", icon: GitFork },
  { href: "/flare/sideways", label: "Think Sideways", icon: Lightbulb },
  { href: "/flare/personas", label: "Personalities", icon: UserCog },
];
const FIELD: NavItem[] = [{ href: "/field", label: "Field Operations", icon: Compass }];
/** Bottom tab bar on phones and portrait tablets: the four places people go most, plus "More" for everything. */
const PRIMARY: NavItem[] = [
  { href: "/", label: "Overview", icon: Home },
  { href: "/chamber", label: "G-sus", icon: Sparkles },
  { href: "/knowledge", label: "Archive", icon: Library },
  { href: "/control", label: "Control", icon: Gauge },
];
const GROUPS: { title: string; tone: string; items: NavItem[] }[] = [
  { title: "G-SUS · intelligence", tone: "text-violet", items: GSUS },
  { title: "Demonkoncernen · infrastructure", tone: "text-cyan", items: DEMON },
  { title: "Commerce", tone: "text-ink-3", items: COMMERCE },
  { title: "Rocky Flare", tone: "text-violet", items: FLARE },
  { title: "Field Ops", tone: "text-gold", items: FIELD },
];

/** The G-SUS sigil: an astrolabe ring (knowledge), an eight-point star (guidance) and a cyan core (the machine). */
export function Sigil({ size = 28 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden className="shrink-0">
      <circle cx="16" cy="16" r="14" fill="none" className="stroke-gold" strokeWidth="1" opacity=".7" />
      <circle cx="16" cy="16" r="10.5" fill="none" className="stroke-line-strong" strokeWidth="1" strokeDasharray="1.5 2" />
      <path d="M16 3.5 L18.2 13.8 L28.5 16 L18.2 18.2 L16 28.5 L13.8 18.2 L3.5 16 L13.8 13.8 Z" className="fill-violet" opacity=".9" />
      <path d="M16 8 L17 15 L24 16 L17 17 L16 24 L15 17 L8 16 L15 15 Z" className="fill-bg" opacity=".55" />
      <circle cx="16" cy="16" r="2.2" className="fill-cyan" />
    </svg>
  );
}
export const RockyMark = Sigil;

type Status = { kill_switch: { engaged?: boolean }; llm_provider: string; cost_today_usd: number; daily_cost_limit_usd: number };

const isActive = (path: string, href: string) =>
  href === "/" ? path === "/" : href === "/flare" ? path === "/flare" : path === href || path.startsWith(href + "/");

const LIVE_LABEL: Record<LiveStatus, string> = { live: "Live feed connected", connecting: "Live feed connecting…", offline: "Live feed offline", paused: "Live feed paused (tab in background)" };

export function Shell({ children }: { children: ReactNode }) {
  const router = useRouter();
  const [ready, setReady] = useState(false);
  useEffect(() => {
    if (!getToken()) router.replace("/login");
    else setReady(true);
  }, [router]);
  if (!ready) return null;
  return <DialogProvider><ShellFrame>{children}</ShellFrame></DialogProvider>;
}

function ShellFrame({ children }: { children: ReactNode }) {
  const path = usePathname();
  const router = useRouter();
  const identity = useIdentity();
  const status = useApi<Status>("/api/system/status");
  const approvals = useApi<any[]>("/api/approvals?status=pending");
  const daemon = useApi<any>("/api/ai/status");
  const { status: live } = useLiveEvents((e) => {
    if (e.type === "kill_switch" || e.type === "task") status.reload();
    if (e.type === "approval") approvals.reload();
  });
  const [drawer, setDrawer] = useState(false);
  const [collapsed, setCollapsed] = useState(false);
  const [typing, setTyping] = useState(false);
  const [online, setOnline] = useState(true);
  useEffect(() => { try { setCollapsed(localStorage.getItem("dk.nav.collapsed") === "1"); } catch { /* storage unavailable */ } }, []);
  useEffect(() => { setDrawer(false); }, [path]);
  useEffect(() => {
    // Ctrl/⌘+K: jump to any page (desktop); the same drawer is "More" on touch devices
    const key = (e: KeyboardEvent) => { if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") { e.preventDefault(); setDrawer((d) => !d); } };
    // on touch screens the tab bar hides while a text field has focus, so it never sits on top of the keyboard / input
    const coarse = window.matchMedia("(pointer: coarse)");
    const isField = (t: EventTarget | null) => t instanceof HTMLElement && (t.isContentEditable || t.tagName === "TEXTAREA" || t.tagName === "SELECT" ||
      (t.tagName === "INPUT" && !["checkbox", "radio", "button", "submit", "range", "file", "color"].includes((t as HTMLInputElement).type)));
    const fin = (e: FocusEvent) => { if (coarse.matches && isField(e.target)) setTyping(true); };
    const fout = () => setTimeout(() => setTyping(isField(document.activeElement) && coarse.matches), 50);
    const net = () => setOnline(navigator.onLine);
    net();
    window.addEventListener("keydown", key);
    document.addEventListener("focusin", fin);
    document.addEventListener("focusout", fout);
    window.addEventListener("online", net);
    window.addEventListener("offline", net);
    return () => {
      window.removeEventListener("keydown", key);
      document.removeEventListener("focusin", fin);
      document.removeEventListener("focusout", fout);
      window.removeEventListener("online", net);
      window.removeEventListener("offline", net);
    };
  }, []);
  const engaged = !!status.data?.kill_switch?.engaged;
  const pending = approvals.data?.length ?? 0;
  const unreachable = !online || (status.error?.startsWith("Cannot reach") ?? false);
  const signOut = () => { setToken(null); router.replace("/login"); };
  const toggleCollapsed = () => setCollapsed((c) => { try { localStorage.setItem("dk.nav.collapsed", c ? "0" : "1"); } catch { /* ignore */ } return !c; });

  return (
    <div className="flex min-h-dvh">
      <a href="#main" className="sr-only z-50 rounded-md bg-violet px-3 py-2 font-semibold text-black focus:not-sr-only focus:fixed focus:left-3 focus:top-3">Skip to content</a>

      {/* desktop: persistent sidebar, collapsible to an icon rail */}
      <aside aria-label="Main navigation" className={`sticky top-0 hidden h-dvh shrink-0 flex-col border-r border-line bg-[#121211]/90 lg:flex ${collapsed ? "w-16" : "w-60"}`}>
        <div className={`flex items-center gap-2.5 pb-3 pt-5 ${collapsed ? "justify-center px-2" : "px-5"}`}>
          <Sigil size={30} />
          {!collapsed && (
            <div className="min-w-0">
              <div className="font-serif text-[15px] font-semibold leading-tight tracking-wide" title={identity.company_name}>{identity.company_name}</div>
              <div className="whitespace-nowrap font-mono text-[9.5px] uppercase tracking-[0.12em] text-ink-3">{identity.platform_name} · head: G-sus</div>
            </div>
          )}
        </div>
        <div className="manuscript-rule mx-3 mb-2" />
        <nav className="flex-1 overflow-y-auto px-2 pb-3">
          <NavGroups path={path} pending={pending} compact={collapsed} />
        </nav>
        <div className={`border-t border-line py-3 text-[11px] text-ink-3 ${collapsed ? "px-2 text-center" : "px-4"}`}>
          <div className={`flex items-center gap-1.5 ${collapsed ? "justify-center" : ""}`} title={LIVE_LABEL[live]}>
            <Activity size={12} className={live === "live" ? "text-good" : "text-ink-3"} aria-hidden />
            {collapsed ? <span className="sr-only">{LIVE_LABEL[live]}</span> : LIVE_LABEL[live]}
          </div>
          <div className={`mt-2 flex items-center gap-3 ${collapsed ? "flex-col" : ""}`}>
            <button className="text-ink-3 underline-offset-2 hover:text-ink-2 hover:underline" onClick={signOut}>Sign out</button>
            <span className="flex-1" />
            <button onClick={toggleCollapsed} aria-pressed={collapsed} aria-label={collapsed ? "Expand navigation" : "Collapse navigation"} title={collapsed ? "Expand navigation" : "Collapse navigation"}
              className="rounded p-1 text-ink-3 hover:bg-surface hover:text-ink-2">
              {collapsed ? <PanelLeftOpen size={15} /> : <PanelLeftClose size={15} />}
            </button>
          </div>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className={`sticky top-0 z-20 border-b pt-[env(safe-area-inset-top)] backdrop-blur ${engaged ? "border-critical/60 bg-critical/15" : "border-line bg-bg/85"}`}>
          <div className="flex items-center gap-x-3 gap-y-1 px-3 py-2 text-[12px] sm:px-6 sm:py-2.5 lg:gap-x-5">
            <Link href="/" className="flex shrink-0 items-center gap-2 lg:hidden" aria-label={`${identity.company_name} — overview`}>
              <Sigil size={24} />
              <span className="hidden font-mono text-[11px] font-bold uppercase tracking-[0.14em] min-[420px]:inline">{identity.company_name.replace("G-SUS & ", "")}</span>
            </Link>
            <Link href="/daemon" className="inline-flex min-h-9 min-w-0 items-center gap-1.5 text-ink-3 hover:text-ink-2" title="DAEMON CORE status">
              {daemon.data?.offline_mode ? <CloudOff size={13} className="shrink-0 text-cyan" /> : <Cpu size={13} className="shrink-0" />}
              <span className={daemon.data?.offline_mode ? "font-mono text-[11px] uppercase tracking-wider text-cyan" : ""}>{daemon.data ? (daemon.data.offline_mode ? "offline" : daemon.data.profile.toLowerCase()) : "…"}</span>
              <span className="hidden truncate md:inline">· AI: <span className={status.data?.llm_provider === "none" ? "text-warning" : "text-ink-2"}>
                {status.data?.llm_provider === "none" ? "not configured" : daemon.data?.active_models?.chat ? `local ${daemon.data.active_models.chat.split("-q")[0]}` : status.data?.llm_provider ?? "…"}</span></span>
            </Link>
            <span className="num hidden text-ink-3 sm:inline">AI spend today: <span className="text-ink-2">${status.data?.cost_today_usd?.toFixed(2) ?? "…"}</span> / ${status.data?.daily_cost_limit_usd ?? "…"}</span>
            <span className="flex-1" />
            <span className="lg:hidden" title={LIVE_LABEL[live]}>
              <Activity size={14} className={live === "live" ? "text-good" : "text-ink-3"} aria-hidden />
              <span className="sr-only">{LIVE_LABEL[live]}</span>
            </span>
            <button onClick={() => setDrawer(true)} className="hidden items-center gap-2 rounded-md border border-line px-2.5 py-1 text-ink-3 hover:border-line-strong hover:text-ink-2 lg:inline-flex"
              aria-label="Find a page (Ctrl+K)">
              <Search size={13} aria-hidden /> Find a page <kbd className="rounded border border-line px-1 font-mono text-[10px]">Ctrl K</kbd>
            </button>
            <KillSwitch engaged={engaged} onChange={status.reload} />
          </div>
          {unreachable && (
            <div role="status" className="flex items-center gap-2 border-t border-warning/40 bg-warning/10 px-3 py-1.5 text-[12.5px] text-warning sm:px-6">
              <WifiOff size={14} aria-hidden />
              <span className="flex-1">{online ? "Cannot reach the Demonkoncernen server — figures may be out of date." : "This device is offline — figures may be out of date; AI and agents need the server."}</span>
              <button className="underline underline-offset-2" onClick={() => { status.reload(); daemon.reload(); approvals.reload(); }}>Retry</button>
            </div>
          )}
        </header>
        <main id="main" tabIndex={-1} className="mx-auto w-full max-w-[1500px] flex-1 px-3 py-5 pb-[calc(5.5rem+env(safe-area-inset-bottom))] outline-none sm:px-5 lg:px-8 lg:py-6 lg:pb-8">
          {children}
        </main>
      </div>

      {/* phones + portrait tablets: bottom tab bar (thumb reach), hidden while typing */}
      <nav aria-label="Primary" className={`fixed inset-x-0 bottom-0 z-30 border-t border-line bg-bg/95 pb-[env(safe-area-inset-bottom)] backdrop-blur lg:hidden ${typing ? "hidden" : ""}`}>
        <ul className="mx-auto flex max-w-2xl">
          {PRIMARY.map(({ href, label, icon: Icon }) => {
            const active = isActive(path, href);
            return (
              <li key={href} className="flex-1">
                <Link href={href} aria-current={active ? "page" : undefined}
                  className={`flex min-h-14 flex-col items-center justify-center gap-0.5 text-[11px] ${active ? "text-violet" : "text-ink-3"}`}>
                  <Icon size={21} aria-hidden />{label}
                </Link>
              </li>
            );
          })}
          <li className="flex-1">
            <button onClick={() => setDrawer(true)} aria-haspopup="dialog" aria-expanded={drawer}
              className="relative flex min-h-14 w-full flex-col items-center justify-center gap-0.5 text-[11px] text-ink-3">
              <MoreHorizontal size={21} aria-hidden />More
              {pending > 0 && <span className="num absolute right-[calc(50%-20px)] top-1.5 rounded bg-violet px-1 text-[10px] font-semibold text-black" aria-label={`${pending} approvals pending`}>{pending}</span>}
            </button>
          </li>
        </ul>
      </nav>

      {drawer && <NavDrawer path={path} pending={pending} live={live} onClose={() => setDrawer(false)} onSignOut={signOut} company={identity.company_name} />}
    </div>
  );
}

function NavGroups({ path, pending, compact = false, filter = "" }: { path: string; pending: number; compact?: boolean; filter?: string }) {
  const f = filter.trim().toLowerCase();
  return (
    <>
      {GROUPS.map((g) => {
        const items = f ? g.items.filter((i) => i.label.toLowerCase().includes(f) || g.title.toLowerCase().includes(f)) : g.items;
        if (!items.length) return null;
        return (
          <div key={g.title} className="mb-2">
            {compact ? <div className="manuscript-rule mx-2 my-2" aria-hidden /> :
              <div className={`px-3 pb-1 pt-2 font-mono text-[9.5px] uppercase tracking-[0.22em] ${g.tone}`}>{g.title}</div>}
            <ul>
              {items.map(({ href, label, icon: Icon }) => {
                const active = isActive(path, href);
                return (
                  <li key={href}>
                    <Link href={href} aria-current={active ? "page" : undefined} aria-label={compact ? label : undefined} title={compact ? label : undefined}
                      className={`flex items-center gap-2.5 rounded-md text-[13px] transition ${compact ? "justify-center px-0 py-2" : "px-3 py-1.5 max-lg:min-h-11 max-lg:text-[15px]"} ${active ? "bg-surface-2 text-ink" : "text-ink-3 hover:bg-surface hover:text-ink-2"}`}>
                      <Icon size={compact ? 17 : 15} className={active ? "text-violet" : ""} aria-hidden />
                      {!compact && <span className="flex-1">{label}</span>}
                      {href === "/approvals" && pending > 0 && (
                        <span className="num rounded bg-violet px-1.5 text-[11px] font-semibold text-black" aria-label={`${pending} pending`}>{pending}</span>
                      )}
                    </Link>
                  </li>
                );
              })}
            </ul>
          </div>
        );
      })}
    </>
  );
}

/** Every page, searchable: "More" on touch devices, Ctrl/⌘+K on desktop. A modal <dialog>: focus stays inside, Esc closes. */
function NavDrawer({ path, pending, live, onClose, onSignOut, company }: { path: string; pending: number; live: LiveStatus; onClose: () => void; onSignOut: () => void; company: string }) {
  const ref = useRef<HTMLDialogElement>(null);
  const [q, setQ] = useState("");
  useEffect(() => {
    const d = ref.current;
    if (d && !d.open) d.showModal();
  }, []);
  const fine = typeof window !== "undefined" && window.matchMedia("(pointer: fine)").matches; // no keyboard pop-up on phones
  return (
    <dialog ref={ref} aria-label="All pages" onCancel={(e) => { e.preventDefault(); onClose(); }} onClick={(e) => { if (e.target === ref.current) onClose(); }}
      className="dk-drawer m-0 h-dvh max-h-none w-full max-w-none border-0 bg-transparent p-0 sm:w-[22rem]">
      <div className="flex h-full flex-col border-r border-line-strong bg-surface pt-[env(safe-area-inset-top)] text-ink">
        <div className="flex items-center gap-2.5 px-4 pb-2 pt-4">
          <Sigil size={26} />
          <div className="min-w-0 flex-1 font-serif text-[15px] font-semibold leading-tight">{company}</div>
          <button onClick={onClose} aria-label="Close" className="flex h-11 w-11 items-center justify-center rounded-md text-ink-3 hover:bg-surface-2 hover:text-ink"><X size={20} /></button>
        </div>
        <div className="px-4 pb-2">
          <label className="relative block">
            <span className="sr-only">Find a page</span>
            <Search size={15} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-ink-3" aria-hidden />
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Find a page…" autoFocus={fine} className="w-full pl-9"
              onKeyDown={(e) => { if (e.key === "Enter") { const a = ref.current?.querySelector<HTMLAnchorElement>("nav a"); a?.click(); } }} />
          </label>
        </div>
        <nav aria-label="All pages" className="flex-1 overflow-y-auto overscroll-contain px-2 pb-3"><NavGroups path={path} pending={pending} filter={q} /></nav>
        <div className="flex items-center gap-3 border-t border-line px-4 py-3 pb-[calc(0.75rem+env(safe-area-inset-bottom))] text-[12px] text-ink-3">
          <Activity size={13} className={live === "live" ? "text-good" : "text-ink-3"} aria-hidden />
          <span className="flex-1">{LIVE_LABEL[live]}</span>
          <button onClick={onSignOut} className="min-h-11 rounded-md px-3 text-ink-2 hover:bg-surface-2">Sign out</button>
        </div>
      </div>
    </dialog>
  );
}

function KillSwitch({ engaged, onChange }: { engaged: boolean; onChange: () => void }) {
  const dlg = useDialog();
  const [busy, setBusy] = useState(false);
  const toggle = async () => {
    let reason = "";
    if (!engaged) {
      const r = await dlg.prompt({ title: "Emergency stop", danger: true, confirmLabel: "Stop all agent work",
        message: "Halts every agent immediately: running tasks stop at their next checkpoint and nothing new starts until you release it.",
        label: "Reason (recorded in the audit log)" });
      if (!r) return;
      reason = r;
    } else if (!(await dlg.confirm({ title: "Release the emergency stop?", message: "Agents resume their queued work.", confirmLabel: "Release" }))) {
      return;
    }
    setBusy(true);
    try { await api("/api/system/kill-switch", { method: "POST", json: { engaged: !engaged, reason } }); onChange(); }
    catch (e) { await dlg.alert({ title: "The emergency stop could not be changed", message: (e as Error).message }); }
    finally { setBusy(false); }
  };
  return (
    <button onClick={toggle} disabled={busy} aria-pressed={engaged}
      className={`inline-flex min-h-9 shrink-0 items-center gap-1.5 rounded-md border px-2.5 py-1 font-mono text-[11px] uppercase tracking-wider ${engaged ? "border-critical bg-critical text-white" : "border-critical/50 text-[#f08a8a] hover:bg-critical/15"}`}>
      <Power size={13} aria-hidden />
      <span className="hidden sm:inline">{engaged ? "Halted · release" : "Emergency stop"}</span>
      <span className="sm:hidden">{engaged ? "Release" : "Stop"}</span>
    </button>
  );
}
