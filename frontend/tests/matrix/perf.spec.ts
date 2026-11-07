/** Loading performance, measured in the browser (not estimated): TTFB, FCP, LCP, CLS, an INP estimate from a real
 *  interaction, JavaScript transferred, DOM size, JS heap. Desktop unthrottled; phone with 4× CPU slowdown and a slow
 *  4G network (150 ms RTT, 1.6 Mbit/s down). Results: test-results/perf.json. Lab numbers on this machine — real
 *  devices and networks differ. */
import { expect, test } from "@playwright/test";
import fs from "node:fs";

const PAGES = ["/login", "/", "/control", "/knowledge", "/chamber"];
const results: Record<string, Record<string, number | string | null>> = {};

for (const profile of ["desktop", "phone (4× CPU, slow 4G)"] as const) {
  test(`performance — ${profile}`, async ({ browser }) => {
    test.setTimeout(240_000);
    const phone = profile !== "desktop";
    const state = JSON.parse(fs.readFileSync("tests/.auth/admin.json", "utf8"));
    // first visit: no service worker (it would serve cached files and bypass the network throttling)
    const ctx = await browser.newContext({ storageState: state, viewport: phone ? { width: 390, height: 844 } : { width: 1440, height: 900 }, isMobile: phone, hasTouch: phone,
                                           serviceWorkers: "block" });
    for (const p of PAGES) {
      const page = await ctx.newPage();
      const cdp = await ctx.newCDPSession(page);
      await cdp.send("Network.enable");
      await cdp.send("Network.setCacheDisabled", { cacheDisabled: true }); // first visit, nothing cached
      if (phone) {
        await cdp.send("Emulation.setCPUThrottlingRate", { rate: 4 });
        await cdp.send("Network.emulateNetworkConditions", { offline: false, latency: 150, downloadThroughput: 1_600_000 / 8, uploadThroughput: 750_000 / 8 });
      }
      await page.addInitScript(() => {
        (window as any).__lcp = 0; (window as any).__cls = 0; (window as any).__inp = 0;
        new PerformanceObserver((l) => { for (const e of l.getEntries()) (window as any).__lcp = e.startTime; }).observe({ type: "largest-contentful-paint", buffered: true });
        (window as any).__shifts = [];
        new PerformanceObserver((l) => { for (const e of l.getEntries() as any[]) if (!e.hadRecentInput) {
          (window as any).__cls += e.value;
          for (const s of e.sources ?? []) (window as any).__shifts.push(`${Math.round(e.value * 1000) / 1000} ${s.node?.nodeName ?? "?"}.${String(s.node?.className ?? "").slice(0, 60)}`);
        } }).observe({ type: "layout-shift", buffered: true });
        new PerformanceObserver((l) => { for (const e of l.getEntries() as any[]) (window as any).__inp = Math.max((window as any).__inp, e.duration); }).observe({ type: "event", buffered: true, durationThreshold: 16 } as any);
      });
      await page.goto(p, { waitUntil: "load" });
      await page.waitForTimeout(phone ? 3000 : 1500);
      // one real interaction for the INP estimate: open and close the page finder / More drawer
      const opener = page.getByRole("button", { name: /^(More|Find a page)/ }).first();
      if (await opener.count()) { await opener.click(); await page.keyboard.press("Escape"); await page.waitForTimeout(300); }
      const m = await page.evaluate(() => {
        const nav = performance.getEntriesByType("navigation")[0] as PerformanceNavigationTiming;
        const res = performance.getEntriesByType("resource") as PerformanceResourceTiming[];
        const fcp = performance.getEntriesByName("first-contentful-paint")[0]?.startTime ?? null;
        const js = res.filter((r) => r.initiatorType === "script" || r.name.endsWith(".js")).reduce((s, r) => s + r.transferSize, 0);
        return { ttfb_ms: Math.round(nav.responseStart), fcp_ms: fcp && Math.round(fcp), lcp_ms: Math.round((window as any).__lcp) || null,
                 cls: Math.round((window as any).__cls * 1000) / 1000, inp_estimate_ms: Math.round((window as any).__inp) || null,
                 dom_content_loaded_ms: Math.round(nav.domContentLoadedEventEnd), js_kb: Math.round(js / 1024),
                 total_kb: Math.round((nav.transferSize + res.reduce((s, r) => s + r.transferSize, 0)) / 1024),
                 dom_nodes: document.getElementsByTagName("*").length, shifted: (window as any).__shifts.slice(0, 4).join(" | ") || null, js_heap_mb: (performance as any).memory ? Math.round((performance as any).memory.usedJSHeapSize / 1048576 * 10) / 10 : null };
      });
      results[`${profile} ${p}`] = m;
      await page.close();
    }
    await ctx.close();
    fs.mkdirSync("test-results", { recursive: true });
    fs.writeFileSync("test-results/perf.json", JSON.stringify(results, null, 1));
    console.table(Object.fromEntries(Object.entries(results).filter(([k]) => k.startsWith(profile))));
    for (const [k, m] of Object.entries(results).filter(([k]) => k.startsWith(profile))) {
      expect(Number(m.cls ?? 0), `${k} layout shift — moved: ${m.shifted}`).toBeLessThanOrEqual(0.1); // "good" threshold
      expect(Number(m.lcp_ms ?? 0), `${k} largest contentful paint`).toBeLessThanOrEqual(phone ? 4000 : 2500); // phone: below "poor"; desktop: "good"
    }
  });
}
