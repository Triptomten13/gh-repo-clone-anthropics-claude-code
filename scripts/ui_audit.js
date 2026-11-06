// UI audit crawler (docs/COMPLETION_AUDIT.md §1): visits every signed-in page and tab and lists buttons without a handler,
// links to unknown routes, console errors, failed API calls and placeholder text. It never clicks action buttons — only tabs.
// Usage: node scripts/ui_audit.js <dir with preview.pw> <out.json> <base url>   (signs in as preview-admin@example.com)
const { chromium } = require("playwright");
const fs = require("fs");
const [W, OUT, BASE] = process.argv.slice(2);
const ROUTES = ["/", "/agents", "/ai", "/approvals", "/archive", "/archivum", "/chamber", "/control", "/daemon", "/experiments", "/field",
  "/finance", "/flare", "/flare/brands", "/flare/campaigns", "/flare/collab", "/flare/mutations", "/flare/personas", "/flare/portfolio",
  "/flare/sideways", "/governance", "/hq", "/knowledge", "/lab", "/portfolio", "/radar", "/research", "/settings", "/demo", "/creative"];
const KNOWN = [...ROUTES, "/welcome", "/status", "/login", "/lab/"];
(async () => {
  const pw = fs.readFileSync(`${W}/preview.pw`, "utf8").trim();
  const r = await (await fetch(`${BASE}/api/auth/login`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ email: "preview-admin@example.com", password: pw }) })).json();
  const b = await chromium.launch();
  const ctx = await b.newContext({ viewport: { width: 1440, height: 1000 }, storageState: { cookies: [], origins: [{ origin: BASE, localStorage: [{ name: "rocky.token", value: r.token }] }] } });
  const report = {};
  for (const route of ROUTES) {
    const p = await ctx.newPage();
    const rep = { console: [], api: [], dead: [], badLinks: [], text: [], tabs: [], empties: [], disabled: [] };
    p.on("console", (m) => m.type() === "error" && rep.console.push(m.text().slice(0, 200)));
    p.on("pageerror", (e) => rep.console.push("PAGEERROR " + e.message.slice(0, 200)));
    p.on("response", (res) => { const u = new URL(res.url()); if (u.pathname.startsWith("/api/") && res.status() >= 400) rep.api.push(`${res.request().method()} ${u.pathname} ${res.status()}`); });
    await p.goto(BASE + route); await p.waitForTimeout(2500);
    const inspect = async (label) => p.evaluate(({ label, KNOWN }) => {
      const out = { dead: [], badLinks: [], text: [], empties: [], disabled: [] };
      const props = (el) => { const k = Object.keys(el).find((k) => k.startsWith("__reactProps$")); return k ? el[k] : null; };
      const main = document.querySelector("#main") || document.body;
      const name = (el) => (el.getAttribute("aria-label") || el.textContent || el.title || "").trim().replace(/\s+/g, " ").slice(0, 60);
      for (const el of main.querySelectorAll("button, [role=button], [role=tab]")) {
        const pr = props(el) || {};
        const form = el.closest("form"); const fp = form ? props(form) : null;
        const submits = (el.type === "submit" || (el.tagName === "BUTTON" && !el.getAttribute("type"))) && form && fp && fp.onSubmit;
        if (el.disabled) { out.disabled.push(`${label}: ${name(el)}${el.title ? " (title: " + el.title.slice(0, 60) + ")" : ""}`); continue; }
        if (!pr.onClick && !pr.onMouseDown && !pr.onPointerDown && !submits && !pr.onKeyDown) out.dead.push(`${label}: <${el.tagName.toLowerCase()}> "${name(el)}"`);
      }
      for (const a of main.querySelectorAll("a[href]")) {
        const h = a.getAttribute("href"); if (!h || h.startsWith("http") || h.startsWith("mailto") || h.startsWith("#") || h.startsWith("blob:") || h.startsWith("data:")) continue;
        const path = h.split(/[?#]/)[0];
        if (path.startsWith("/api/")) continue;
        if (!KNOWN.some((k) => k.endsWith("/") ? path.startsWith(k) : path === k)) out.badLinks.push(`${label}: ${h} "${name(a)}"`);
      }
      const t = main.innerText;
      for (const re of [/\bTODO\b/i, /coming soon/i, /lorem ipsum/i, /not implemented/i, /placeholder/i, /\bmock(ed)?\b/i, /\bNaN\b/, /undefined/, /\[object Object\]/, /Invalid Date/]) { const m = t.match(re); if (m) { const i = t.search(re); out.text.push(`${label}: ${re} … ${t.slice(Math.max(0, i - 60), i + 60).replace(/\s+/g, " ")}`); } }
      for (const e of main.querySelectorAll("[data-empty], .empty-state")) out.empties.push(`${label}: ${e.textContent.trim().slice(0, 80)}`);
      return out;
    }, { label, KNOWN });
    const merge = (o) => { for (const k of Object.keys(o)) rep[k].push(...o[k]); };
    merge(await inspect("main"));
    const tabs = await p.locator("#main [role=tab]").all();
    for (let i = 0; i < tabs.length; i++) {
      const t = p.locator("#main [role=tab]").nth(i); const nm = ((await t.textContent()) || "").trim().slice(0, 30);
      rep.tabs.push(nm);
      try { await t.click({ timeout: 3000 }); await p.waitForTimeout(1500); merge(await inspect(`tab ${nm}`)); } catch (e) { rep.console.push(`tab ${nm} click failed`); }
    }
    for (const k of Object.keys(rep)) rep[k] = [...new Set(rep[k])];
    report[route] = rep;
    process.stdout.write(`${route} dead=${rep.dead.length} links=${rep.badLinks.length} api=${rep.api.length} console=${rep.console.length} text=${rep.text.length} disabled=${rep.disabled.length}\n`);
    await p.close();
  }
  fs.writeFileSync(OUT, JSON.stringify(report, null, 1));
  await b.close();
})().catch((e) => { console.error(e); process.exit(1); });
