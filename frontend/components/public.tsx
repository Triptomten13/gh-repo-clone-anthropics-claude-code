"use client";
/** Public pages (no sign-in): landing page and system status. They read only public endpoints
 *  (/api/auth/status, /api/status) and never show private data. */
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";
import { Sigil } from "@/components/shell";
import { api, getToken, startDemoSession } from "@/lib/api";
import { useIdentity } from "@/lib/identity";

export type PublicStatus = {
  name: string; version: string; commit: string; environment: string; demo_mode: boolean; overall: string; checked_at: string; uptime_s: number;
  components: { id: string; name: string; kind: "core" | "optional"; status: string; detail?: string }[];
  features: { name: string; status: string; where?: string; note?: string }[];
};

export function usePublicStatus() {
  const [data, setData] = useState<PublicStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const load = () => api<PublicStatus>("/api/status").then((d) => { setData(d); setError(null); }).catch((e) => setError((e as Error).message));
  useEffect(() => { load(); }, []);
  return { data, error, reload: load };
}

/** Enter the app at `href`: on a public demo server a visitor without a session gets a temporary one first. */
export function useEnter(demoMode: boolean) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const enter = async (href: string) => {
    setError(null);
    if (!getToken() && demoMode) {
      setBusy(true);
      try { await startDemoSession(); } catch (e) { setError((e as Error).message); setBusy(false); return; }
      setBusy(false);
    }
    router.push(getToken() ? href : "/login");
  };
  return { enter, busy, error };
}

export function PublicFrame({ children, demoMode }: { children: ReactNode; demoMode: boolean | null }) {
  const identity = useIdentity();
  return (
    <div className="min-h-dvh">
      <header className="border-b border-line bg-bg/85 pt-[env(safe-area-inset-top)] backdrop-blur">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-4 gap-y-2 px-4 py-3 sm:px-6">
          <Link href="/welcome" className="flex min-w-0 items-center gap-2.5">
            <Sigil size={28} />
            <span className="truncate font-serif text-[16px] font-semibold">{identity.company_name}</span>
          </Link>
          <span className="flex-1" />
          <nav aria-label="Public" className="flex items-center gap-4 text-[13px] text-ink-2">
            <Link className="hover:text-ink" href="/status">Status</Link>
            <Link className="hover:text-ink" href="/welcome#docs">Docs</Link>
            <Link className="rounded-md border border-line px-3 py-1.5 hover:border-line-strong hover:text-ink" href="/login">
              {demoMode ? "Demo or sign in" : "Sign in"}</Link>
          </nav>
        </div>
      </header>
      <main id="main" className="mx-auto max-w-6xl px-4 pb-16 pt-8 sm:px-6">{children}</main>
      <footer className="border-t border-line py-6 text-center text-[12px] text-ink-3">
        {identity.company_name} · governed AI agent platform · {demoMode ? "public demo: synthetic sample data, isolated from the private Control Center" : "private deployment"}
      </footer>
    </div>
  );
}

const FEATURE_TONE: Record<string, string> = {
  available: "border-good/50 text-[#5fd35f]", demo: "border-violet-dim text-violet", config_required: "border-warning/50 text-warning",
  unavailable: "border-line-strong text-ink-3", planned: "border-line text-ink-3",
};
const FEATURE_LABEL: Record<string, string> = {
  available: "available", demo: "works on demo data", config_required: "configuration required", unavailable: "unavailable here", planned: "planned",
};
export function FeatureStatus({ status }: { status: string }) {
  return <span className={`inline-flex whitespace-nowrap rounded border px-1.5 py-px font-mono text-[10px] uppercase tracking-wider ${FEATURE_TONE[status] ?? FEATURE_TONE.unavailable}`}>
    {FEATURE_LABEL[status] ?? status}</span>;
}
