import { expect, test } from "@playwright/test";
import { openShell } from "../helpers";

test("governance: verify the audit chain, export it, replay a run, read the role matrix", async ({ page }) => {
  // an execution to replay
  await openShell(page, "/control");
  await page.locator("#ask-q").fill("12% of 250");
  await page.getByRole("button", { name: "Ask", exact: true }).click();
  await expect(page.getByText("30").first()).toBeVisible();

  await openShell(page, "/governance#audit");
  await page.getByRole("tab", { name: "Audit & compliance" }).click();
  await page.getByRole("button", { name: "Verify now" }).click();
  await expect(page.getByText(/records verified/)).toBeVisible();
  const [dl] = await Promise.all([page.waitForEvent("download"), page.getByRole("button", { name: "Export signed ZIP" }).click()]);
  expect(dl.suggestedFilename()).toBe("demonkoncernen-audit.zip");

  await page.getByRole("tab", { name: "Runs & replay" }).click();
  await page.getByRole("button", { name: /^#\d+$/ }).first().click();
  await expect(page.getByText("not a re-execution")).toBeVisible();

  await page.getByRole("tab", { name: "Identity & roles" }).click();
  await expect(page.getByText("approval.decide").first()).toBeVisible();
});

test("a G-sus run links to its own trace, which opens straight into the replay", async ({ page }) => {
  await openShell(page, "/chamber");
  await page.locator("#objective").fill("Do something nice");  // too vague: G-sus asks instead of guessing — and the run is still traced
  await page.getByRole("button", { name: "Ask G-sus" }).click();
  const link = page.getByRole("link", { name: /Trace & replay · run #\d+/ });
  await expect(link).toBeVisible();
  const id = (await link.textContent())!.match(/#(\d+)/)![1];
  await link.click();
  await expect(page).toHaveURL(new RegExp(`/governance#runs/${id}$`));
  await expect(page.getByText(`Replay · run #${id}`)).toBeVisible();
  await expect(page.getByText("not a re-execution")).toBeVisible();
  await expect(page.locator("li").filter({ hasText: /^1\s*plan/ }).first()).toBeVisible();
});
