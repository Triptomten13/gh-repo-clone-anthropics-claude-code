/** Automated accessibility (axe-core, WCAG 2.0/2.1/2.2 A + AA rules) on the main pages, desktop and phone.
 *  Automated checks find roughly a third of real issues — keyboard and screen-reader passes are still manual (docs). */
import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import fs from "node:fs";

const PAGES = ["/login", "/welcome", "/status", "/", "/control", "/chamber", "/knowledge", "/daemon", "/research", "/agents", "/approvals", "/settings", "/governance", "/demo", "/creative", "/autonomy"];
const report: Record<string, unknown> = {};

for (const [label, viewport] of [["desktop", { width: 1440, height: 900 }], ["phone", { width: 390, height: 844 }]] as const) {
  test(`no serious or critical accessibility violations — ${label}`, async ({ browser }) => {
    test.setTimeout(180_000);
    const state = JSON.parse(fs.readFileSync("tests/.auth/admin.json", "utf8"));
    const ctx = await browser.newContext({ storageState: state, viewport, hasTouch: label === "phone", isMobile: label === "phone" });
    const page = await ctx.newPage();
    const found: string[] = [];
    for (const p of PAGES) {
      if (p === "/login") await ctx.clearCookies();
      await page.goto(p);
      await page.waitForTimeout(800);
      // eslint-disable-next-line @typescript-eslint/no-explicit-any -- axe ships Page types from a newer Playwright; same runtime API
      const r = await new AxeBuilder({ page: page as any }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]).analyze();
      report[`${label} ${p}`] = r.violations.map((v) => ({ id: v.id, impact: v.impact, nodes: v.nodes.length, example: v.nodes[0]?.target }));
      for (const v of r.violations) if (v.impact === "serious" || v.impact === "critical") found.push(`${p}: ${v.id} (${v.impact}) ×${v.nodes.length} e.g. ${JSON.stringify(v.nodes[0]?.target)}`);
    }
    fs.mkdirSync("test-results", { recursive: true });
    fs.writeFileSync(`test-results/a11y-${label}.json`, JSON.stringify(report, null, 1));
    expect(found, found.join("\n")).toEqual([]);
    await ctx.close();
  });
}
