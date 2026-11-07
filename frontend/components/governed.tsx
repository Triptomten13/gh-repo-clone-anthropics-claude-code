"use client";
/** Result of a governed change (policy, budget, grant, access, egress, gate, retention): either applied at once, or filed
 *  as an approval that someone else must approve — then applied here or in the Approval Center. The server repeats the
 *  stored request with every check (docs/COMPLETION_AUDIT.md); this component only shows and asks. */
import Link from "next/link";
import { useState } from "react";
import { Button } from "@/components/ui";
import { api } from "@/lib/api";

export function GovernedResult({ res, onApplied }: { res: any; onApplied?: () => void }) {
  const [state, setState] = useState<{ msg: string; ok: boolean } | null>(null);
  const [busy, setBusy] = useState(false);
  if (!res) return null;
  if (res.status === "pending_approval") {
    const apply = async () => {
      setBusy(true);
      try { await api(`/api/approvals/${res.approval_id}/apply`, { method: "POST" }); setState({ msg: "Applied.", ok: true }); onApplied?.(); }
      catch (e) { setState({ msg: (e as Error).message, ok: false }); } finally { setBusy(false); }
    };
    if (state?.ok) return <div role="status" className="mt-3 rounded-md border border-good/40 bg-good/10 px-3 py-2 text-[13px] text-good">Applied with approval #{res.approval_id}.</div>;
    return (
      <div role="status" className="mt-3 rounded-md border border-warning/40 bg-warning/10 px-3 py-2 text-[13px] text-warning">
        Filed as approval <Link className="underline" href={`/approvals?id=${res.approval_id}`}>#{res.approval_id}</Link> ({res.category}).
        Nothing has changed yet: another approver must approve it, then apply it here or in the Approval Center.
        <div className="mt-2 flex flex-wrap items-center gap-2"><Button busy={busy} onClick={apply}>Apply once approved</Button>
          {state && !state.ok && <span className="text-[12px] text-ink-2">{state.msg}</span>}</div>
      </div>
    );
  }
  return <div role="status" className="mt-3 rounded-md border border-good/40 bg-good/10 px-3 py-2 text-[13px] text-good">Applied.</div>;
}
