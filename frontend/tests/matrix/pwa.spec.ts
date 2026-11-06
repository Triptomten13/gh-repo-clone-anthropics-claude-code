/** Installable app + honest offline behaviour (Chromium: the DevTools protocol gives Chrome's own installability verdict). */
import { expect, test } from "@playwright/test";
import { spawn } from "node:child_process";
import fs from "node:fs";
import path from "node:path";

const token = () => JSON.parse(fs.readFileSync("tests/.auth/admin.json", "utf8")).origins[0].localStorage[0].value as string;

test("installable: manifest, service worker, nothing from the API in any cache", async ({ page, context }) => {
  await page.goto("/");
  await page.evaluate(() => navigator.serviceWorker.ready);
  await page.reload();
  await expect.poll(() => page.evaluate(() => !!navigator.serviceWorker.controller)).toBe(true);
  const cdp = await context.newCDPSession(page);
  expect((await cdp.send("Page.getInstallabilityErrors")).installabilityErrors).toEqual([]);
  expect((await cdp.send("Page.getAppManifest")).errors).toEqual([]);
  for (const p of ["/control", "/knowledge", "/chamber"]) { await page.goto(p); await page.waitForTimeout(700); }
  const cached = await page.evaluate(async () => {
    const out: string[] = [];
    for (const k of await caches.keys()) for (const r of await (await caches.open(k)).keys()) out.push(new URL(r.url).pathname);
    return out;
  });
  expect(cached).toContain("/offline.html");
  expect(cached.filter((u) => u.startsWith("/api") || u === "/health")).toEqual([]);
});

test("offline: server gone → shell + banner or offline page; device offline → banner; server back → recovers", async ({ browser }) => {
  const dir = path.resolve(".next/standalone");
  test.skip(!!process.env.E2E_BASE_URL || !fs.existsSync(path.join(dir, "server.js")), "needs the local standalone build");
  test.setTimeout(120_000);
  const PORT = 3290;
  const B = `http://127.0.0.1:${PORT}`;
  const start = () => spawn("node", ["server.js"], { cwd: dir, env: { ...process.env, PORT: String(PORT), HOSTNAME: "127.0.0.1" }, stdio: "ignore" });
  let srv = start();
  try {
    await expect.poll(async () => (await fetch(`${B}/login`).catch(() => null))?.status ?? 0, { timeout: 20_000 }).toBe(200);
    const ctx = await browser.newContext({ storageState: { cookies: [], origins: [{ origin: B, localStorage: [{ name: "rocky.token", value: token() }] }] } });
    const page = await ctx.newPage();
    const errors: string[] = [];
    page.on("pageerror", (e) => errors.push(e.message));
    await page.goto(`${B}/`);
    await page.evaluate(() => navigator.serviceWorker.ready);
    await page.reload();
    for (const p of ["/control", "/chamber"]) { await page.goto(B + p); await page.waitForTimeout(1200); }
    srv.kill("SIGKILL");
    await page.waitForTimeout(500);
    await page.goto(`${B}/control`);
    await expect(page.locator("#main")).toBeVisible();
    await expect(page.locator("header").getByText("Cannot reach the Demonkoncernen server")).toBeVisible(); // the shell banner
    await page.goto(`${B}/flare/brands`); // never opened → self-contained offline page
    await expect(page.getByRole("heading", { name: "No connection to Demonkoncernen" })).toBeVisible();
    await ctx.setOffline(true);
    await page.goto(`${B}/chamber`);
    await expect(page.locator("header").getByText("This device is offline")).toBeVisible();
    await ctx.setOffline(false);
    srv = start();
    await expect.poll(async () => (await fetch(`${B}/login`).catch(() => null))?.status ?? 0, { timeout: 20_000 }).toBe(200);
    await page.goto(`${B}/control`);
    await expect(page.locator("header").getByText("Cannot reach the Demonkoncernen server")).toHaveCount(0);
    expect(errors).toEqual([]);
    await ctx.close();
  } finally {
    srv.kill("SIGKILL");
  }
});
