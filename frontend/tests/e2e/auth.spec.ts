import { expect, test } from "@playwright/test";
import { ADMIN, isCompact, openShell } from "../helpers";

test.describe("signed out", () => {
  test.use({ storageState: { cookies: [], origins: [] } });

  test("protected pages lead to sign-in; a wrong password is explained; the session survives a reload", async ({ page }) => {
    await page.goto("/control");
    await expect(page).toHaveURL(/\/login$/);
    await page.getByLabel("Email").fill(ADMIN.email);
    await page.getByLabel(/^Password/).fill("not-the-password-1");
    await page.getByRole("button", { name: "Sign in" }).click();
    await expect(page.getByText("invalid credentials")).toBeVisible();
    await page.getByLabel(/^Password/).fill(ADMIN.password);
    await page.getByRole("button", { name: "Sign in" }).click();
    await expect(page).toHaveURL(/\/$/);
    await page.reload();
    await expect(page.locator("#main")).toBeVisible();
  });
});

test("sign out ends the session on this device", async ({ page }) => {
  await openShell(page, "/");
  if (isCompact(page)) {
    await page.getByRole("navigation", { name: "Primary" }).getByRole("button", { name: "More" }).click();
    await page.getByRole("dialog", { name: "All pages" }).getByRole("button", { name: "Sign out" }).click();
  } else {
    await page.getByRole("complementary", { name: "Main navigation" }).getByRole("button", { name: "Sign out" }).click();
  }
  await expect(page).toHaveURL(/\/login$/);
  await page.goto("/control");
  await expect(page).toHaveURL(/\/login$/);
});
