import { expect, test } from "@playwright/test";
import { isCompact, openShell } from "../helpers";

test("Archive: upload a file, find it by search, delete it", async ({ page }) => {
  const marker = `zephyrine${Date.now().toString(36)}`;
  await openShell(page, "/knowledge");
  await page.getByRole("tab", { name: "Documents" }).click();
  await page.locator('input[type="file"]').setInputFiles({ name: `${marker}.txt`, mimeType: "text/plain",
    buffer: Buffer.from(`Field report ${marker}: the northern depot received forty lanterns and two compasses.`) });
  await page.getByRole("button", { name: "Ingest" }).click();
  await expect(page.getByRole("button", { name: "Delete document (admin)" })).toBeVisible({ timeout: 30_000 });
  await page.getByRole("tab", { name: "Search" }).click();
  await page.getByLabel("search query").fill(marker);
  await page.getByLabel("mode").selectOption("keyword");
  await page.getByRole("button", { name: "Search", exact: true }).click();
  await expect(page.getByText(`Field report ${marker}`).first()).toBeVisible();
  await page.getByRole("tab", { name: "Documents" }).click();
  await page.getByRole("button", { name: marker }).first().click();
  await page.getByRole("button", { name: "Delete document (admin)" }).click();
  const dlg = page.getByRole("dialog");
  await expect(dlg).toContainText("cannot be undone");
  await dlg.getByRole("button", { name: "Delete permanently" }).click();
  await page.getByRole("tab", { name: "Search" }).click();
  await page.getByLabel("search query").fill(marker);
  await page.getByRole("button", { name: "Search", exact: true }).click();
  await expect(page.getByText("No relevant passages")).toBeVisible();
});

test("Emergency stop: engage with a reason, release with confirmation", async ({ page }) => {
  await openShell(page, "/control");
  await page.getByRole("button", { name: /^(Emergency stop|Stop)$/ }).click();
  const dlg = page.getByRole("dialog", { name: "Emergency stop" });
  await expect(dlg).toBeVisible();
  await expect(dlg.getByRole("button", { name: "Stop all agent work" })).toBeDisabled(); // a reason is required
  await dlg.getByLabel("Reason (recorded in the audit log)").fill(`e2e ${test.info().project.name}`);
  await dlg.getByRole("button", { name: "Stop all agent work" }).click();
  const release = page.getByRole("button", { name: /^(Halted · release|Release)$/ });
  await expect(release).toHaveAttribute("aria-pressed", "true");
  await release.click();
  await page.getByRole("dialog", { name: "Release the emergency stop?" }).getByRole("button", { name: "Release" }).click();
  await expect(page.getByRole("button", { name: /^(Emergency stop|Stop)$/ })).toHaveAttribute("aria-pressed", "false");
});

test("Ask DAEMON: a calculation is solved without any model", async ({ page }) => {
  await openShell(page, "/control");
  await page.locator("#ask-q").fill("25% of 480");
  await page.getByRole("button", { name: "Ask", exact: true }).click();
  await expect(page.getByText("120").first()).toBeVisible();
  await expect(page.getByText("deterministic").first()).toBeVisible();
});

test("G-sus conversation: streams an answer, or says honestly that no AI is configured", async ({ page }) => {
  await openShell(page, "/chamber");
  const input = page.getByPlaceholder("Talk to G-sus in the selected mode…");
  if (!(await input.count())) {
    await expect(page.getByText("Conversation needs an AI provider")).toBeVisible();
    return;
  }
  test.setTimeout(240_000);
  await input.fill("In one sentence: what is Demonkoncernen AB?");
  await input.press("Enter").catch(() => {});
  const send = page.getByRole("button", { name: /send/i });
  if (await send.isEnabled().catch(() => false)) await send.click();
  await expect(page.locator("pre").filter({ hasText: /\w{3,}/ }).first()).toBeVisible({ timeout: 180_000 });
});

test("Memory export downloads a file", async ({ page }) => {
  await openShell(page, "/knowledge");
  await page.getByRole("tab", { name: "Memory" }).click();
  const [dl] = await Promise.all([page.waitForEvent("download"), page.getByRole("button", { name: "Export JSON" }).click()]);
  expect(dl.suggestedFilename()).toBe("gsus-memory-export.json");
});

test("live feed connects through the same origin", async ({ page }) => {
  await openShell(page, "/control");
  const label = isCompact(page) ? page.locator("header").getByText("Live feed connected") : page.getByRole("complementary").getByText("Live feed connected");
  await expect(label).toBeAttached({ timeout: 15_000 });
});

test("on touch screens the tab bar steps aside while typing", async ({ page }) => {
  test.skip(!isCompact(page) || !test.info().project.use.hasTouch, "touch layouts only");
  await openShell(page, "/control");
  const tabs = page.getByRole("navigation", { name: "Primary" });
  await expect(tabs).toBeVisible();
  await page.locator("#ask-q").focus();
  await expect(tabs).toBeHidden();
  await page.locator("#ask-q").blur();
  await expect(tabs).toBeVisible();
});
