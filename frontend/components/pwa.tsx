"use client";
/** Service-worker registration, "update available" notice and the install button.
 *  Browsers only allow service workers on secure origins (HTTPS or localhost): on a plain-HTTP LAN address the app
 *  still works, it just is not installable and has no offline page — see docs/CROSS_PLATFORM.md (HTTPS on the LAN). */
import { Download, RefreshCw } from "lucide-react";
import { useEffect, useState } from "react";

type InstallEvent = Event & { prompt: () => Promise<void>; userChoice: Promise<{ outcome: string }> };
let deferred: InstallEvent | null = null;
let userAcceptedUpdate = false; // reload ONLY after "Update" — not when the first service worker takes control
const installListeners = new Set<(v: boolean) => void>();

export function PwaRegister() {
  const [waiting, setWaiting] = useState<ServiceWorker | null>(null);
  useEffect(() => {
    const onPrompt = (e: Event) => { e.preventDefault(); deferred = e as InstallEvent; installListeners.forEach((l) => l(true)); };
    window.addEventListener("beforeinstallprompt", onPrompt);
    if (process.env.NODE_ENV !== "production" || !("serviceWorker" in navigator) || !window.isSecureContext) return () => window.removeEventListener("beforeinstallprompt", onPrompt);
    let reloading = false;
    const onController = () => { if (userAcceptedUpdate && !reloading) { reloading = true; location.reload(); } };
    navigator.serviceWorker.addEventListener("controllerchange", onController);
    navigator.serviceWorker.register("/sw.js").then((reg) => {
      if (reg.waiting && navigator.serviceWorker.controller) setWaiting(reg.waiting);
      reg.addEventListener("updatefound", () => {
        const sw = reg.installing;
        sw?.addEventListener("statechange", () => { if (sw.state === "installed" && navigator.serviceWorker.controller) setWaiting(sw); });
      });
      const check = () => { if (document.visibilityState === "visible") reg.update().catch(() => {}); };
      document.addEventListener("visibilitychange", check);
    }).catch(() => { /* registration refused (e.g. private mode): the app works without it */ });
    return () => {
      window.removeEventListener("beforeinstallprompt", onPrompt);
      navigator.serviceWorker.removeEventListener("controllerchange", onController);
    };
  }, []);
  if (!waiting) return null;
  return (
    <div role="status" className="fixed inset-x-3 bottom-[calc(4.5rem+env(safe-area-inset-bottom))] z-40 mx-auto flex max-w-md items-center gap-3 rounded-lg border border-violet-dim bg-surface-2 px-4 py-3 text-[13px] shadow-xl lg:bottom-6">
      <RefreshCw size={15} className="shrink-0 text-violet" aria-hidden />
      <span className="flex-1">A new version of Demonkoncernen is ready.</span>
      <button onClick={() => { userAcceptedUpdate = true; waiting.postMessage("SKIP_WAITING"); }} className="min-h-9 rounded-md bg-violet px-3 font-semibold text-black">Update</button>
    </div>
  );
}

/** Shown only where the browser offers installation (Chrome/Edge desktop, Android). iOS: Share → Add to Home Screen. */
export function InstallButton({ className = "" }: { className?: string }) {
  const [can, setCan] = useState(false);
  useEffect(() => {
    setCan(!!deferred);
    installListeners.add(setCan);
    return () => { installListeners.delete(setCan); };
  }, []);
  if (!can) return null;
  return (
    <button className={`inline-flex items-center gap-1.5 ${className}`} onClick={async () => {
      if (!deferred) return;
      await deferred.prompt();
      await deferred.userChoice;
      deferred = null;
      installListeners.forEach((l) => l(false));
    }}>
      <Download size={13} aria-hidden /> Install app
    </button>
  );
}
