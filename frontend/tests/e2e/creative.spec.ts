import { expect, test } from "@playwright/test";
import { openShell } from "../helpers";

// The test stack has no AI model installed: the Creative Intelligence Center must say so instead of pretending.
test("creative intelligence: a tournament without models fails honestly; routing explains its decision", async ({ page }) => {
  await openShell(page, "/creative");
  await page.locator("#brief").fill("Skriv en låt om vinterns första snö med refräng");
  await page.getByRole("button", { name: "Start tournament" }).click();
  await expect(page.getByText(/Tournament #\d+/).first()).toBeVisible();
  await expect(page.getByText(/no permitted model can do this task here/).first()).toBeVisible({ timeout: 20_000 });

  await page.getByRole("tab", { name: "Routing" }).click();
  await page.getByRole("button", { name: "Decide" }).click();
  await expect(page.getByText("songwriting · sv").first()).toBeVisible();
  await expect(page.getByText(/no permitted model can do this task here|first for songwriting/).first()).toBeVisible();

  await page.getByRole("tab", { name: "Model quality" }).click();
  await expect(page.getByText(/Measured quality by task/)).toBeVisible();
  await page.getByRole("tab", { name: "Providers & health" }).click();
  await expect(page.getByText(/never routable until validated/)).toBeVisible();
  await page.getByRole("tab", { name: "Costs" }).click();
  await expect(page.getByText(/Value per resource unit/)).toBeVisible();
});
