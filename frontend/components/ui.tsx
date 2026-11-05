"use client";
import { AlertTriangle, CheckCircle2, CircleDashed, Loader2, OctagonX, ShieldAlert, ShieldCheck, ShieldQuestion } from "lucide-react";
import type { ReactNode } from "react";

export function PageHeader({ title, kicker, children }: { title: string; kicker?: string; children?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div>
        {kicker && <div className="mb-1 font-mono text-[11px] uppercase tracking-[0.2em] text-ember">{kicker}</div>}
        <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
      </div>
      <div className="flex flex-wrap items-center gap-2">{children}</div>
    </div>
  );
}

export function Card({ title, action, children, className = "", pad = true }: { title?: ReactNode; action?: ReactNode; children: ReactNode; className?: string; pad?: boolean }) {
  return (
    <section className={`rounded-lg border border-line bg-surface ${className}`}>
      {title && (
        <header className="flex items-center justify-between gap-2 border-b border-line px-4 py-2.5">
          <h2 className="font-mono text-[11px] uppercase tracking-[0.16em] text-ink-2">{title}</h2>
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
      <div className={`num mt-1 text-2xl font-semibold tracking-tight ${accent ? "text-ember" : ""}`}>{value}</div>
      {sub && <div className="mt-0.5 text-xs text-ink-3">{sub}</div>}
    </div>
  );
}

type BtnProps = { children: ReactNode; onClick?: () => void; variant?: "primary" | "ghost" | "danger"; disabled?: boolean; busy?: boolean; type?: "button" | "submit"; title?: string };
export function Button({ children, onClick, variant = "ghost", disabled, busy, type = "button", title }: BtnProps) {
  const styles = {
    primary: "bg-ember text-black hover:brightness-110 font-semibold",
    ghost: "border border-line-strong text-ink-2 hover:bg-surface-2 hover:text-ink",
    danger: "border border-critical/60 text-[#f08a8a] hover:bg-critical/15",
  }[variant];
  return (
    <button type={type} title={title} onClick={onClick} disabled={disabled || busy}
      className={`inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-[13px] transition disabled:cursor-not-allowed disabled:opacity-40 ${styles}`}>
      {busy && <Loader2 size={13} className="animate-spin" />}
      {children}
    </button>
  );
}

export function DemoBadge({ show }: { show?: boolean }) {
  if (!show) return null;
  return <span className="ml-1.5 rounded border border-ember-dim px-1 py-px font-mono text-[9.5px] tracking-wider text-ember" title="Synthetic sample data, not market data">DEMO</span>;
}

const STATUS: Record<string, { cls: string; icon: ReactNode; label?: string }> = {
  succeeded: { cls: "text-[#5fd35f] border-good/40", icon: <CheckCircle2 size={12} /> },
  approved: { cls: "text-[#5fd35f] border-good/40", icon: <ShieldCheck size={12} /> },
  executed: { cls: "text-[#5fd35f] border-good/40", icon: <CheckCircle2 size={12} /> },
  running: { cls: "text-series-1 border-series-1/40", icon: <Loader2 size={12} className="animate-spin" /> },
  queued: { cls: "text-ink-2 border-line-strong", icon: <CircleDashed size={12} /> },
  pending: { cls: "text-warning border-warning/40", icon: <CircleDashed size={12} /> },
  needs_review: { cls: "text-warning border-warning/40", icon: <ShieldQuestion size={12} />, label: "needs review" },
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
        <div className="h-full rounded-full bg-ember" style={{ width: `${score}%`, opacity: 0.45 + 0.55 * (confidence ?? 0.5) }} />
      </div>
      <span className="num w-9 text-right text-[13px] font-medium">{score.toFixed(0)}</span>
      {confidence !== undefined && confidence !== null && <span className="num text-[11px] text-ink-3">c{(confidence * 100).toFixed(0)}</span>}
    </div>
  );
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

export function Table({ head, children }: { head: ReactNode[]; children: ReactNode }) {
  return (
    <div className="overflow-x-auto">
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
    <label className="flex flex-col gap-1 text-[12px] text-ink-3">
      <span>{label}</span>
      {children}
    </label>
  );
}
