/** Public demo on a phone (Pixel 7 emulation — not a physical device). */
import { expect, test } from "@playwright/test";
import { startDemo } from "./helpers";

test("mobile navigation: landing page, demo tab bar, page drawer, no sideways scroll", async ({ page }) => {
  await startDemo(page);
  const bar = page.getByRole("navigation", { name: "Primary" });
  await expect(bar.getByRole("link", { name: "Demo" })).toBeVisible();
  await bar.getByRole("link", { name: "G-sus" }).click();
  await expect(page).toHaveURL(/\/chamber$/);
  await bar.getByRole("button", { name: "More" }).click();
  await page.getByRole("dialog").getByRole("link", { name: "Demo Center" }).click();
  await expect(page).toHaveURL(/\/demo$/);
  // (not "networkidle": the live event stream keeps a connection open by design)
  for (const [p, text] of [["/welcome", "What works on this server"], ["/status", "All core services operational"], ["/demo", "Evaluate a sample product"]]) {
    await page.goto(p);
    await expect(page.getByText(text).first()).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth), p).toBeLessThanOrEqual(0);
  }
});
