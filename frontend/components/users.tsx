"use client";
import { useDialog } from "@/components/dialog";
import { useState } from "react";
import { Button, Card, ErrorBanner, Field, StatusBadge, Table } from "@/components/ui";
import { ago, api, setToken } from "@/lib/api";
import { useApi } from "@/lib/hooks";

const input = "rounded-md border border-line-strong bg-bg px-2.5 py-1.5 text-[13px] text-ink outline-none focus:border-violet";

/** Admin-only user management. Every change signs the affected user out (token version bump) and is audited. */
export function UsersCard() {
  const users = useApi<any[]>("/api/auth/users");
  const me = useApi<any>("/api/auth/me");
  const [err, setErr] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [form, setForm] = useState({ email: "", password: "", role: "operator" });
  const dlg = useDialog();
  const act = async (fn: () => Promise<unknown>, ok: string) => {
    try { await fn(); setMsg(ok); setErr(null); users.reload(); } catch (e) { setErr((e as Error).message); setMsg(null); }
  };
  if (users.error?.includes("requires role")) {
    return <Card title="Users & access"><p className="text-[13px] text-ink-3">Only admins can manage users. Ask an admin, or on the server run <code className="text-ink-2">python -m app.cli list-users</code>.</p></Card>;
  }
  return (
    <Card title="Users & access" pad={false}>
      <div className="p-4 pb-0"><ErrorBanner error={err} />{msg && <div className="mb-3 text-[12.5px] text-good">{msg}</div>}</div>
      <Table head={["User", "Role", "Status", "Created", ""]}>
        {(users.data ?? []).map((u) => (
          <tr key={u.id}>
            <td className="font-medium">{u.email}{u.email === me.data?.email && <span className="ml-1.5 text-[11px] text-ink-3">(you)</span>}</td>
            <td>
              <select aria-label={`Role for ${u.email}`} className={input} value={u.role} disabled={u.email === me.data?.email}
                onChange={(e) => act(() => api(`/api/auth/users/${u.id}`, { method: "PATCH", json: { role: e.target.value } }), `${u.email} is now ${e.target.value} (signed out)`)}>
                <option value="admin">admin</option><option value="operator">operator</option><option value="viewer">viewer</option>
              </select>
            </td>
            <td><StatusBadge status={u.disabled ? "disabled" : "active"} /></td>
            <td className="text-ink-3">{ago(u.created_at)}</td>
            <td className="whitespace-nowrap text-right">
              {u.email !== me.data?.email && <>
                <Button onClick={async () => { const pw = await dlg.prompt({ title: `Reset password for ${u.email}`, message: "All of this user's sessions are signed out.", label: "New password", inputType: "password", minLength: 10, confirmLabel: "Reset password", danger: true }); if (pw) act(() => api(`/api/auth/users/${u.id}/password`, { method: "POST", json: { password: pw } }), `Password reset for ${u.email}`); }}>Reset password</Button>{" "}
                <Button variant={u.disabled ? "ghost" : "danger"} onClick={() => act(() => api(`/api/auth/users/${u.id}`, { method: "PATCH", json: { disabled: !u.disabled } }), `${u.email} ${u.disabled ? "enabled" : "disabled"}`)}>{u.disabled ? "Enable" : "Disable"}</Button>
              </>}
            </td>
          </tr>
        ))}
      </Table>
      <form className="flex flex-wrap items-end gap-2 border-t border-line p-4" onSubmit={(e) => { e.preventDefault(); act(() => api("/api/auth/users", { method: "POST", json: form }), `Created ${form.email}`).then(() => setForm({ email: "", password: "", role: "operator" })); }}>
        <Field label="Email"><input className={input} type="email" required value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} /></Field>
        <Field label="Initial password (≥10)"><input className={input} type="password" minLength={10} required value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} /></Field>
        <Field label="Role"><select className={input} value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })}><option>operator</option><option>viewer</option><option>admin</option></select></Field>
        <Button type="submit" variant="primary">Add user</Button>
      </form>
      <p className="px-4 pb-4 text-[11.5px] text-ink-3">Locked out? On the server: <code className="text-ink-2">python -m app.cli reset-password --email you@example.com</code>. Roles: admin (everything, incl. approvals, models, keys), operator (run work), viewer (read only).</p>
    </Card>
  );
}

export function PasswordCard() {
  const [cur, setCur] = useState("");
  const [nw, setNw] = useState("");
  const [state, setState] = useState<{ ok?: string; err?: string }>({});
  return (
    <Card title="Your password">
      <form className="flex flex-wrap items-end gap-2" onSubmit={async (e) => {
        e.preventDefault();
        try { const r = await api<{ token: string }>("/api/auth/password", { method: "POST", json: { current_password: cur, new_password: nw } }); setToken(r.token); setState({ ok: "Changed. Other sessions were signed out." }); setCur(""); setNw(""); }
        catch (x) { setState({ err: (x as Error).message }); }
      }}>
        <Field label="Current password"><input className={input} type="password" required value={cur} onChange={(e) => setCur(e.target.value)} /></Field>
        <Field label="New password (≥10)"><input className={input} type="password" minLength={10} required value={nw} onChange={(e) => setNw(e.target.value)} /></Field>
        <Button type="submit">Change password</Button>
      </form>
      {state.ok && <div className="mt-2 text-[12.5px] text-good">{state.ok}</div>}
      {state.err && <div className="mt-2 text-[12.5px] text-[#f3a5a5]">{state.err}</div>}
    </Card>
  );
}
