"use client";
/** Accessible, touch-friendly replacements for window.confirm / prompt / alert.
 *  Native <dialog> + showModal(): real modal semantics, focus kept inside, Escape closes, backdrop. Full-width sheet at
 *  the bottom on phones (thumb reach, above the keyboard), centred card on larger screens. Secrets use a masked field. */
import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";

type Ask = {
  kind: "confirm" | "prompt" | "alert";
  title: string;
  message?: string;
  label?: string;
  inputType?: "text" | "password" | "url";
  minLength?: number;
  confirmLabel?: string;
  danger?: boolean;
  resolve: (v: any) => void;
};
type Api = {
  confirm: (o: { title: string; message?: string; confirmLabel?: string; danger?: boolean }) => Promise<boolean>;
  prompt: (o: { title: string; message?: string; label: string; inputType?: "text" | "password" | "url"; minLength?: number; confirmLabel?: string; danger?: boolean }) => Promise<string | null>;
  alert: (o: { title: string; message?: string }) => Promise<void>;
};

const Ctx = createContext<Api | null>(null);

export function useDialog(): Api {
  const c = useContext(Ctx);
  if (!c) throw new Error("useDialog needs <DialogProvider>");
  return c;
}

export function DialogProvider({ children }: { children: ReactNode }) {
  const [ask, setAsk] = useState<Ask | null>(null);
  const open = useCallback((a: Omit<Ask, "resolve">) => new Promise<any>((resolve) => setAsk({ ...a, resolve })), []);
  const api: Api = {
    confirm: (o) => open({ kind: "confirm", ...o }),
    prompt: (o) => open({ kind: "prompt", ...o }),
    alert: (o) => open({ kind: "alert", ...o }),
  };
  return (
    <Ctx.Provider value={api}>
      {children}
      {ask && <DialogView ask={ask} done={(v) => { ask.resolve(v); setAsk(null); }} />}
    </Ctx.Provider>
  );
}

function DialogView({ ask, done }: { ask: Ask; done: (v: any) => void }) {
  const ref = useRef<HTMLDialogElement>(null);
  const [value, setValue] = useState("");
  useEffect(() => {
    const d = ref.current;
    if (d && !d.open) d.showModal();
  }, []);
  const cancel = () => done(ask.kind === "confirm" ? false : ask.kind === "prompt" ? null : undefined);
  const tooShort = ask.kind === "prompt" && value.trim().length < (ask.minLength ?? 1);
  return (
    <dialog ref={ref} aria-labelledby="dk-dialog-title" onCancel={(e) => { e.preventDefault(); cancel(); }}
      className="dk-dialog m-0 mt-auto w-full max-w-none rounded-t-2xl border border-line-strong bg-surface p-0 text-ink sm:m-auto sm:max-w-md sm:rounded-xl">
      <form method="dialog" className="p-5 pb-[calc(1.25rem+env(safe-area-inset-bottom))] sm:pb-5"
        onSubmit={(e) => { e.preventDefault(); if (ask.kind === "prompt") { if (!tooShort) done(value.trim()); } else done(true); }}>
        <h2 id="dk-dialog-title" className="font-serif text-[18px] font-semibold">{ask.title}</h2>
        {ask.message && <p className="mt-2 whitespace-pre-line text-[14px] text-ink-2">{ask.message}</p>}
        {ask.kind === "prompt" && (
          <label className="mt-4 block text-[13px] text-ink-2">
            {ask.label}
            <input autoFocus type={ask.inputType ?? "text"} value={value} onChange={(e) => setValue(e.target.value)} minLength={ask.minLength}
              autoComplete={ask.inputType === "password" ? "new-password" : "off"} className="mt-1.5 block w-full" />
            {ask.minLength && ask.minLength > 1 && <span className="mt-1 block text-[12px] text-ink-3">at least {ask.minLength} characters</span>}
          </label>
        )}
        <div className="mt-5 flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
          {ask.kind !== "alert" && (
            <button type="button" onClick={cancel} className="min-h-11 rounded-md border border-line-strong px-4 text-[14px] text-ink-2 hover:bg-surface-2 sm:min-h-9">Cancel</button>
          )}
          <button type="submit" autoFocus={ask.kind !== "prompt"} disabled={tooShort}
            className={`min-h-11 rounded-md px-4 text-[14px] font-semibold disabled:opacity-40 sm:min-h-9 ${ask.danger ? "bg-critical text-white" : "bg-violet text-black"}`}>
            {ask.confirmLabel ?? (ask.kind === "alert" ? "OK" : ask.kind === "confirm" ? "Confirm" : "Save")}
          </button>
        </div>
      </form>
    </dialog>
  );
}
