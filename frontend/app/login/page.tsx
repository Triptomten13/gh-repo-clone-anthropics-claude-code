"use client";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { RockyMark } from "@/components/shell";
import { Button, ErrorBanner, Field } from "@/components/ui";
import { api, setToken } from "@/lib/api";

export default function Login() {
  const router = useRouter();
  const [setup, setSetup] = useState<boolean | null>(null);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    api<{ setup_required: boolean }>("/api/auth/status").then((r) => setSetup(r.setup_required)).catch((e) => setError(`API unreachable: ${e.message}`));
  }, []);
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      const r = await api<{ token: string }>(setup ? "/api/auth/setup" : "/api/auth/login", { method: "POST", json: { email, password } });
      setToken(r.token);
      router.replace("/");
    } catch (err) { setError((err as Error).message); } finally { setBusy(false); }
  };
  return (
    <div className="flex min-h-screen items-center justify-center px-4">
      <form onSubmit={submit} className="w-full max-w-sm rounded-xl border border-line bg-surface p-7">
        <div className="mb-6 flex items-center gap-3">
          <RockyMark size={36} />
          <div>
            <div className="font-mono text-lg font-bold tracking-[0.32em]">ROCKY</div>
            <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-ink-3">Commerce Intelligence HQ</div>
          </div>
        </div>
        <ErrorBanner error={error} />
        {setup && <p className="mb-4 text-[13px] text-ink-2">First run: create the administrator account. Admins approve launches, spend and compliance decisions.</p>}
        <div className="space-y-3">
          <Field label="Email"><input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="username" /></Field>
          <Field label="Password (min. 10 characters)"><input type="password" required minLength={10} value={password} onChange={(e) => setPassword(e.target.value)} autoComplete={setup ? "new-password" : "current-password"} /></Field>
        </div>
        <div className="mt-5"><Button variant="primary" type="submit" busy={busy} disabled={setup === null}>{setup ? "Create admin & enter" : "Sign in"}</Button></div>
      </form>
    </div>
  );
}
