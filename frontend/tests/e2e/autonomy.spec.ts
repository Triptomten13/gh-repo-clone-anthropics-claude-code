import { expect, test } from "@playwright/test";
import { openShell } from "../helpers";

// Model Hunter, Championship, Devil's Advocate, Account Vault. No live network: the Hub search is not clicked here (the
// real discovery run is documented in docs/AUTONOMY.md); the test stack has no local models, so no championship can run.

test("the Devil's Advocate is calibrated, reviews a decision and says why", async ({ page }) => {
  await openShell(page, "/autonomy#advocate");
  await expect(page.getByText("Calibration").first()).toBeVisible();
  await expect(page.getByText(/^9\/9$/).first()).toBeVisible(); // every known-bad case flagged, every known-good case passed
  await page.getByRole("button", { name: "Review", exact: true }).click();
  await expect(page.getByRole("status").filter({ hasText: /concern/ })).toBeVisible(); // the example has no evidence and no verification
});

test("Account Vault: a proposal is challenged, then waits for a second approver; nothing secret is shown", async ({ page }) => {
  await openShell(page, "/autonomy#vault");
  await expect(page.getByText(/never receive a password or key/)).toBeVisible();
  const name = `e2e-org-${Date.now() % 100000}`;
  await page.getByLabel("Account / organisation name").fill(name);
  await page.getByLabel("Purpose").fill("higher Hub rate limits for the Model Hunter");
  for (const q of ["1.", "2.", "3.", "4.", "5.", "6.", "7.", "8.", "9.", "10."]) await page.getByLabel(new RegExp(`^${q.replace(".", "\\.")} `)).fill("answered");
  await page.getByRole("button", { name: "Propose" }).click();
  await expect(page.getByRole("status").filter({ hasText: /pending approval — approval #\d+/ })).toBeVisible();
  await expect(page.getByRole("cell", { name: new RegExp(name) })).toBeVisible();
});

test("Model Hunter and Championship explain themselves on a machine without models", async ({ page }) => {
  await openShell(page, "/autonomy");
  await expect(page.getByText(/Screening happens before anything is downloaded/)).toBeVisible();
  await page.getByRole("tab", { name: "Championship" }).click();
  await expect(page.getByText(/Same tasks · same hardware · same run/)).toBeVisible();
  await expect(page.getByRole("button", { name: "Start a championship" })).toBeDisabled(); // no installed model to compete
});
