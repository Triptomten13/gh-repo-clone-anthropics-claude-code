import { expect, test } from "@playwright/test";
import { isCompact, openShell } from "../helpers";

test("navigate with this device's controls (tab bar + More on touch, sidebar + Ctrl+K on desktop)", async ({ page }) => {
  await openShell(page, "/");
  if (isCompact(page)) {
    const tabs = page.getByRole("navigation", { name: "Primary" });
    await expect(tabs).toBeVisible();
    await expect(tabs.getByRole("link")).toHaveCount(4);
    await tabs.getByRole("link", { name: "Control" }).click();
    await expect(page).toHaveURL(/\/control$/);
    await expect(tabs.getByRole("link", { name: "Control" })).toHaveAttribute("aria-current", "page");
    await tabs.getByRole("button", { name: "More" }).click();
    const drawer = page.getByRole("dialog", { name: "All pages" });
    await expect(drawer).toBeVisible();
    await drawer.getByPlaceholder("Find a page…").fill("agent");
    await expect(drawer.getByRole("link")).toHaveCount(1);
    await drawer.getByRole("link", { name: "Agent Registry" }).click();
    await expect(page).toHaveURL(/\/agents$/);
    await expect(drawer).toBeHidden();
    await page.goBack(); // the browser / Android back button
    await expect(page).toHaveURL(/\/control$/);
  } else {
    const side = page.getByRole("complementary", { name: "Main navigation" });
    await side.getByRole("link", { name: "Control Center" }).click();
    await expect(page).toHaveURL(/\/control$/);
    const toggle = side.getByRole("button", { name: "Collapse navigation" });
    await toggle.click();
    await page.reload();
    await expect(side.getByRole("button", { name: "Expand navigation" })).toHaveAttribute("aria-pressed", "true"); // remembered
    await side.getByRole("button", { name: "Expand navigation" }).click();
    await page.keyboard.press("Control+k");
    const finder = page.getByRole("dialog", { name: "All pages" });
    await expect(finder).toBeVisible();
    await finder.getByPlaceholder("Find a page…").fill("research");
    await page.keyboard.press("Enter");
    await expect(page).toHaveURL(/\/research$/);
    await page.keyboard.press("Control+k");
    await expect(finder).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(finder).toBeHidden();
  }
});

test("keyboard users can skip straight to the content", async ({ page }) => {
  test.skip(isCompact(page) && !!test.info().project.use.isMobile, "phones have no Tab key");
  await openShell(page, "/control");
  await page.keyboard.press("Tab");
  await expect(page.getByRole("link", { name: "Skip to content" })).toBeFocused();
});
