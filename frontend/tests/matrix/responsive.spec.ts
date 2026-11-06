/** Layout at the widths people actually use, portrait and landscape, with touch where devices have it.
 *  Every page: no sideways scrolling, navigation reachable, no console errors. Chromium emulation — not a physical device. */
import { expect, test, type Browser } from "@playwright/test";
import fs from "node:fs";
import { ROUTES } from "../helpers";

const SIZES: [string, number, number, boolean][] = [
  ["320 small phone", 320, 568, true], ["375 phone", 375, 667, true], ["390 iPhone", 390, 844, true], ["430 large phone", 430, 932, true],
  ["768 tablet portrait", 768, 1024, true], ["1024 tablet landscape / small laptop", 1024, 768, true], ["1280 laptop", 1280, 800, false],
  ["1440 desktop", 1440, 900, false], ["1920 large desktop", 1920, 1080, false], ["844×390 phone landscape", 844, 390, true],
  ["1180×820 iPad landscape", 1180, 820, true],
];

async function context(browser: Browser, w: number, h: number, touch: boolean) {
  const state = JSON.parse(fs.readFileSync("tests/.auth/admin.json", "utf8"));
  return browser.newContext({ storageState: state, viewport: { width: w, height: h }, hasTouch: touch, isMobile: touch && w < 1000 });
}

for (const [label, w, h, touch] of SIZES) {
  test(`every page fits at ${label}`, async ({ browser }) => {
    test.setTimeout(180_000);
    const ctx = await context(browser, w, h, touch);
    const page = await ctx.newPage();
    const errors: string[] = [];
    page.on("console", (m) => { if (m.type() === "error") errors.push(`${page.url()}: ${m.text().slice(0, 140)}`); });
    page.on("pageerror", (e) => errors.push(`${page.url()}: ${e.message.slice(0, 140)}`));
    const problems: string[] = [];
    for (const r of ROUTES) {
      await page.goto(r);
      await expect(page.locator("#main")).toBeVisible();
      await page.waitForTimeout(400);
      const m = await page.evaluate(() => ({
        overflow: document.documentElement.scrollWidth - window.innerWidth,
        nav: [...document.querySelectorAll('nav[aria-label="Primary"] a, aside[aria-label="Main navigation"] a')].filter((a) => (a as HTMLElement).offsetParent !== null).length,
      }));
      if (m.overflow > 0) problems.push(`${r}: ${m.overflow}px sideways scroll`);
      if (m.nav === 0) problems.push(`${r}: no navigation visible`);
    }
    expect(problems, problems.join("\n")).toEqual([]);
    expect(errors, errors.join("\n")).toEqual([]);
    await ctx.close();
  });
}

test("states beyond the first screen fit on a small phone too (open document, navigation drawer, dialog)", async ({ browser }) => {
  const ctx = await context(browser, 320, 568, true);
  const page = await ctx.newPage();
  const fits = async (what: string) => expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth), what).toBeLessThanOrEqual(0);
  await page.goto("/knowledge");
  await page.getByRole("tab", { name: "Documents" }).click();
  await page.locator('input[type="file"]').setInputFiles({ name: "a-deliberately-long-file-name-without-any-break-at-all-2026.txt", mimeType: "text/plain", buffer: Buffer.from("Responsive probe about lanterns and compasses.") });
  await page.getByRole("button", { name: "Ingest" }).click();
  await expect(page.getByRole("button", { name: "Delete document (admin)" })).toBeVisible();
  await fits("open document");
  await page.getByRole("button", { name: "Delete document (admin)" }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await fits("confirmation dialog");
  await page.getByRole("dialog").getByRole("button", { name: "Delete permanently" }).click();
  await page.getByRole("navigation", { name: "Primary" }).getByRole("button", { name: "More" }).click();
  await expect(page.getByRole("dialog", { name: "All pages" })).toBeVisible();
  await fits("navigation drawer");
  await ctx.close();
});
