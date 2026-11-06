"use client";
import { AlertTriangle, CheckCircle2, CircleDashed, Loader2, OctagonX, ShieldAlert, ShieldCheck, ShieldQuestion } from "lucide-react";
import { useEffect, useRef, useState, type ReactNode } from "react";

export function PageHeader({ title, kicker, children }: { title: string; kicker?: string; children?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div>
        {kicker && <div className="mb-1 font-mono text-[11px] uppercase tracking-[0.2em] text-violet">{kicker}</div>}
        <h1 className="font-serif text-[28px] font-semibold leading-tight tracking-tight">{title}</h1>
      </div>
      <div className="flex flex-wrap items-center gap-2">{children}</div>
    </div>
  );
}

export function Card({ title, action, children, className = "", pad = true }: { title?: ReactNode; action?: ReactNode; children: ReactNode; className?: string; pad?: boolean }) {
  return (
    <section className={`min-w-0 rounded-lg border border-line bg-surface ${className}`}>
      {title && (
        <header className="flex flex-wrap items-center justify-between gap-2 border-b border-line px-4 py-2.5">
          <h2 className="min-w-0 font-mono text-[11px] uppercase tracking-[0.16em] text-ink-2 [overflow-wrap:anywhere]">{title}</h2>
          {action}
        </header>
      )}
      <div className={pad ? "p-4" : ""}>{children}</div>
    </section>
  );
}

export function Stat({ label, value, sub, accent = false }: { label: string; value: ReactNode; sub?: ReactNode; accent?: boolean }) {
  return (
    <div className="rounded-lg border border-line bg-surface px-4 py-3">
      <div className="font-mono text-[10.5px] uppercase tracking-[0.16em] text-ink-3">{label}</div>
      <div className={`num mt-1 text-2xl font-semibold tracking-tight ${accent ? "text-violet" : ""}`}>{value}</div>
      {sub && <div className="mt-0.5 text-xs text-ink-3">{sub}</div>}
    </div>
  );
}

type BtnProps = { children: ReactNode; onClick?: () => void; variant?: "primary" | "ghost" | "danger"; disabled?: boolean; busy?: boolean; type?: "button" | "submit"; title?: string };
export function Button({ children, onClick, variant = "ghost", disabled, busy, type = "button", title }: BtnProps) {
  const styles = {
    primary: "bg-violet text-black hover:brightness-110 font-semibold",
    ghost: "border border-line-strong text-ink-2 hover:bg-surface-2 hover:text-ink",
    danger: "border border-critical/60 text-[#f08a8a] hover:bg-critical/15",
  }[variant];
  return (
    <button type={type} title={title} onClick={onClick} disabled={disabled || busy}
      className={`inline-flex items-center justify-center gap-1.5 rounded-md px-3 py-1.5 text-[13px] transition pointer-coarse:min-h-10 disabled:cursor-not-allowed disabled:opacity-40 ${styles}`}>
      {busy && <Loader2 size={13} className="animate-spin" />}
      {children}
    </button>
  );
}

export function DemoBadge({ show }: { show?: boolean }) {
  if (!show) return null;
  return <span className="ml-1.5 rounded border border-violet-dim px-1 py-px font-mono text-[9.5px] tracking-wider text-violet" title="Synthetic sample data, not market data">DEMO</span>;
}

const STATUS: Record<string, { cls: string; icon: ReactNode; label?: string }> = {
  succeeded: { cls: "text-[#5fd35f] border-good/40", icon: <CheckCircle2 size={12} /> },
  approved: { cls: "text-[#5fd35f] border-good/40", icon: <ShieldCheck size={12} /> },
  executed: { cls: "text-[#5fd35f] border-good/40", icon: <CheckCircle2 size={12} /> },
  running: { cls: "text-series-1 border-series-1/40", icon: <Loader2 size={12} className="animate-spin" /> },
  queued: { cls: "text-ink-2 border-line-strong", icon: <CircleDashed size={12} /> },
  pending: { cls: "text-warning border-warning/40", icon: <CircleDashed size={12} /> },
  needs_review: { cls: "text-warning border-warning/40", icon: <ShieldQuestion size={12} />, label: "needs review" },
  waiting_for_approval: { cls: "text-warning border-warning/40", icon: <ShieldQuestion size={12} />, label: "waiting for approval" },
  needs_clarification: { cls: "text-warning border-warning/40", icon: <ShieldQuestion size={12} />, label: "needs clarification" },
  restricted: { cls: "text-serious border-serious/40", icon: <ShieldAlert size={12} /> },
  unreviewed: { cls: "text-ink-3 border-line-strong", icon: <ShieldQuestion size={12} /> },
  blocked: { cls: "text-[#f08a8a] border-critical/50", icon: <OctagonX size={12} /> },
  failed: { cls: "text-[#f08a8a] border-critical/50", icon: <AlertTriangle size={12} /> },
  rejected: { cls: "text-[#f08a8a] border-critical/50", icon: <OctagonX size={12} /> },
  cancelled: { cls: "text-ink-3 border-line-strong", icon: <OctagonX size={12} /> },
  suspended: { cls: "text-[#f08a8a] border-critical/50", icon: <OctagonX size={12} /> },
  active: { cls: "text-[#5fd35f] border-good/40", icon: <CheckCircle2 size={12} /> },
  configured: { cls: "text-[#5fd35f] border-good/40", icon: <CheckCircle2 size={12} /> },
  missing_credentials: { cls: "text-warning border-warning/40", icon: <AlertTriangle size={12} />, label: "missing credentials" },
  not_implemented: { cls: "text-ink-3 border-line-strong", icon: <CircleDashed size={12} />, label: "planned" },
  installed: { cls: "text-[#5fd35f] border-good/40", icon: <CheckCircle2 size={12} /> },
  operational: { cls: "text-[#5fd35f] border-good/40", icon: <CheckCircle2 size={12} /> },
  healthy: { cls: "text-[#5fd35f] border-good/40", icon: <CheckCircle2 size={12} /> },
  completed: { cls: "text-[#5fd35f] border-good/40", icon: <CheckCircle2 size={12} /> },
  fits: { cls: "text-[#5fd35f] border-good/40", icon: <CheckCircle2 size={12} /> },
  permitted: { cls: "text-[#5fd35f] border-good/40", icon: <ShieldCheck size={12} />, label: "commercial use ok" },
  review_required: { cls: "text-warning border-warning/40", icon: <ShieldQuestion size={12} />, label: "licence review" },
  downloading: { cls: "text-series-1 border-series-1/40", icon: <Loader2 size={12} className="animate-spin" /> },
  available: { cls: "text-ink-2 border-line-strong", icon: <CircleDashed size={12} />, label: "not installed" },
  tight: { cls: "text-warning border-warning/40", icon: <AlertTriangle size={12} />, label: "tight fit" },
  unverified: { cls: "text-warning border-warning/40", icon: <ShieldQuestion size={12} /> },
  proposed: { cls: "text-warning border-warning/40", icon: <CircleDashed size={12} /> },
  not_integrated: { cls: "text-ink-3 border-line-strong", icon: <CircleDashed size={12} />, label: "no adapter" },
  removed: { cls: "text-ink-3 border-line-strong", icon: <OctagonX size={12} /> },
  disabled: { cls: "text-ink-3 border-line-strong", icon: <OctagonX size={12} /> },
  revoked: { cls: "text-ink-3 border-line-strong", icon: <OctagonX size={12} /> },
  paused: { cls: "text-warning border-warning/40", icon: <OctagonX size={12} /> },
  unreachable: { cls: "text-[#f08a8a] border-critical/50", icon: <AlertTriangle size={12} /> },
  does_not_fit: { cls: "text-[#f08a8a] border-critical/50", icon: <OctagonX size={12} />, label: "does not fit" },
  no_runtime: { cls: "text-[#f08a8a] border-critical/50", icon: <OctagonX size={12} />, label: "no runtime" },
  blocked_no_consent: { cls: "text-[#f08a8a] border-critical/50", icon: <OctagonX size={12} />, label: "blocked: no consent" },
};

/** Status chip: always icon + label, never color alone. */
export function StatusBadge({ status }: { status: string }) {
  const s = STATUS[status] ?? { cls: "text-ink-2 border-line-strong", icon: <CircleDashed size={12} /> };
  return (
    <span className={`inline-flex items-center gap-1 whitespace-nowrap rounded border px-1.5 py-0.5 text-[11px] ${s.cls}`}>
      {s.icon}{s.label ?? status.replaceAll("_", " ")}
    </span>
  );
}

export function Epistemic({ kind }: { kind: string }) {
  const map: Record<string, string> = { verified: "border-good/40 text-[#5fd35f]", estimate: "border-series-1/40 text-series-1",
    assumption: "border-warning/40 text-warning", hypothesis: "border-[#9085e9]/50 text-[#b4acf0]" };
  return <span className={`rounded border px-1.5 py-px font-mono text-[10px] uppercase tracking-wider ${map[kind] ?? "border-line text-ink-3"}`}>{kind}</span>;
}

export function ScoreBar({ score, confidence }: { score: number | null; confidence?: number | null }) {
  if (score === null || score === undefined) return <span className="text-ink-3">—</span>;
  return (
    <div className="flex items-center gap-2" title={`score ${score} · data coverage ${confidence ?? "?"}`}>
      <div className="h-1.5 w-20 overflow-hidden rounded-full bg-surface-2">
        <div className="h-full rounded-full bg-violet" style={{ width: `${score}%`, opacity: 0.45 + 0.55 * (confidence ?? 0.5) }} />
      </div>
      <span className="num w-9 text-right text-[13px] font-medium">{score.toFixed(0)}</span>
      {confidence !== undefined && confidence !== null && <span className="num text-[11px] text-ink-3">c{(confidence * 100).toFixed(0)}</span>}
    </div>
  );
}

/** Where a value comes from — never colour-only, never implied. */
const SOURCE: Record<string, { label: string; cls: string; title: string }> = {
  live: { label: "LIVE DATA", cls: "border-good/50 text-[#5fd35f]", title: "Read from this server's database" },
  demo: { label: "DEMO DATA", cls: "border-violet-dim text-violet", title: "Synthetic sample records — not real business data" },
  simulated: { label: "SIMULATED OUTPUT", cls: "border-warning/50 text-warning", title: "Not produced by a model, tool or database" },
  connected: { label: "CONNECTED SERVICE", cls: "border-cyan/50 text-cyan", title: "A service this server actually reached" },
  unavailable: { label: "UNAVAILABLE SERVICE", cls: "border-line-strong text-ink-3", title: "Not configured or disabled on this server" },
  rules: { label: "RULE-BASED · NO AI MODEL", cls: "border-gold/50 text-gold", title: "Computed by deterministic rules and heuristics, not by a language model" },
};
export function SourceLabel({ kind }: { kind: keyof typeof SOURCE | string }) {
  const s = SOURCE[kind] ?? SOURCE.unavailable;
  return <span title={s.title} className={`inline-flex items-center whitespace-nowrap rounded border px-1.5 py-px font-mono text-[9.5px] tracking-wider ${s.cls}`}>{s.label}</span>;
}

export function ErrorBanner({ error }: { error: string | null }) {
  if (!error) return null;
  return <div className="mb-4 rounded-md border border-critical/50 bg-critical/10 px-3 py-2 text-sm text-[#f3a5a5]">{error}</div>;
}

export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="rounded-md border border-dashed border-line-strong px-6 py-10 text-center">
      <div className="text-sm font-medium text-ink-2">{title}</div>
      {children && <div className="mx-auto mt-1.5 max-w-md text-[13px] text-ink-3">{children}</div>}
    </div>
  );
}

export function Table({ head, children, label = "Table" }: { head: ReactNode[]; children: ReactNode; label?: string }) {
  // when the table is wider than the screen (phones), its scroll area must be reachable by keyboard and named
  const ref = useRef<HTMLDivElement>(null);
  const [scrolls, setScrolls] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const check = () => setScrolls(el.scrollWidth > el.clientWidth + 1);
    check();
    const ro = new ResizeObserver(check);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return (
    <div ref={ref} className="overflow-x-auto" {...(scrolls ? { tabIndex: 0, role: "region", "aria-label": `${label} (scrolls sideways)` } : {})}>
      <table className="w-full border-collapse text-[13px]">
        <thead>
          <tr className="border-b border-line text-left font-mono text-[10.5px] uppercase tracking-[0.12em] text-ink-3">
            {head.map((h, i) => <th key={i} className="whitespace-nowrap px-3 py-2 font-normal">{h}</th>)}
          </tr>
        </thead>
        <tbody className="[&>tr]:border-b [&>tr]:border-line/60 [&>tr:hover]:bg-surface-2/60 [&_td]:px-3 [&_td]:py-2">{children}</tbody>
      </table>
    </div>
  );
}

export function Json({ value }: { value: unknown }) {
  return <pre className="max-h-96 overflow-auto rounded-md bg-bg p-3 font-mono text-[11.5px] leading-relaxed text-ink-2">{JSON.stringify(value, null, 2)}</pre>;
}

export function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="flex min-w-0 flex-col gap-1 text-[12px] text-ink-3">
      <span>{label}</span>
      {children}
    </label>
  );
}

const EVIDENCE: Record<string, { label: string; glyph: string; cls: string }> = {
  historical_fact: { label: "historical fact", glyph: "◆", cls: "border-good/50 text-[#5fd35f]" },
  primary_source: { label: "primary source", glyph: "❦", cls: "border-gold/60 text-gold" },
  religious_interpretation: { label: "religious interpretation", glyph: "✧", cls: "border-violet/60 text-violet" },
  philosophical_theory: { label: "philosophical theory", glyph: "∴", cls: "border-cyan/50 text-cyan" },
  scholarly_hypothesis: { label: "scholarly hypothesis", glyph: "?", cls: "border-series-1/60 text-series-1" },
  speculative: { label: "speculative claim", glyph: "≈", cls: "border-warning/50 text-warning" },
  fiction_canon: { label: "fictional canon", glyph: "✶", cls: "border-[#e879f9]/50 text-[#f0abfc]" },
  unclassified: { label: "unclassified", glyph: "·", cls: "border-line-strong text-ink-3" },
};
export const EVIDENCE_CLASSES = Object.keys(EVIDENCE);

/** Evidentiary status chip — glyph + words, never colour alone. */
export function EvidenceBadge({ kind }: { kind: string }) {
  const e = EVIDENCE[kind] ?? EVIDENCE.unclassified;
  return <span className={`inline-flex items-center gap-1 whitespace-nowrap rounded border px-1.5 py-px text-[11px] ${e.cls}`} title="evidentiary status"><span aria-hidden>{e.glyph}</span>{e.label}</span>;
}
