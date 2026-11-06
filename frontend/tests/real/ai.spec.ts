/** Real AI and agent workflows on a phone-sized touch screen, against a running instance WITH local models.
 *  Opt-in (needs models + a running server):  E2E_AI=1 E2E_BASE_URL=http://<lan-ip>:3000 E2E_EMAIL=… E2E_PASSWORD=… \
 *    npx playwright test --project=setup --project=real-ai */
import { expect, test } from "@playwright/test";

test("G-sus conversation streams a real reply", async ({ page }) => {
  test.setTimeout(300_000);
  await page.goto("/chamber");
  const input = page.getByPlaceholder("Talk to G-sus in the selected mode…");
  await expect(input, "this instance has no streaming AI provider").toBeVisible();
  await input.fill("In two sentences: what is Demonkoncernen AB?");
  await page.getByRole("button", { name: "Send" }).click();
  const out = page.locator("pre").filter({ hasText: /\w/ }).first();
  await expect(out).toBeVisible({ timeout: 240_000 });
  const early = (await out.innerText()).length;
  await expect.poll(async () => (await out.innerText()).length, { timeout: 120_000, message: "text must keep arriving while streaming" }).toBeGreaterThan(early);
});

test("a multi-agent G-sus run survives leaving the screen and coming back", async ({ page }) => {
  test.setTimeout(600_000);
  const objective = `Summarise in three bullet points what a field lantern product needs (e2e ${Date.now().toString(36)})`;
  await page.goto("/chamber");
  await page.locator("#objective").fill(objective);
  await page.getByRole("button", { name: "Ask G-sus" }).click();
  const recent = page.getByRole("button", { name: new RegExp(objective.slice(-12)) });
  await expect(recent).toBeVisible({ timeout: 60_000 });
  await page.getByRole("navigation", { name: "Primary" }).getByRole("link", { name: "Control" }).click(); // leave
  await expect(page).toHaveURL(/\/control$/);
  await page.getByRole("navigation", { name: "Primary" }).getByRole("link", { name: "G-sus" }).click(); // come back
  await expect(recent).toBeVisible();
  await expect.poll(async () => (await recent.innerText()).toLowerCase(), { timeout: 540_000, intervals: [5000] }).toMatch(/completed|succeeded|awaiting|blocked|failed/);
  console.log("run status after return:", (await recent.innerText()).replace(/\s+/g, " "));
});

test("Control Center shows the active local models and real measurements", async ({ page }) => {
  await page.goto("/control");
  await expect(page.getByText(/qwen|smollm|nomic/i).first()).toBeVisible({ timeout: 20_000 });
  await expect(page.getByText("RAM in use")).toBeVisible();
  await expect(page.getByText(/of [\d.]+ GB/).first()).toBeVisible();
});
