import { expect, type Page } from "@playwright/test";

/** Arrive as an anonymous visitor and start a demo session from the landing page, like a person would. */
export async function startDemo(page: Page) {
  await page.goto("/");
  await expect(page).toHaveURL(/\/welcome$/);
  await page.getByRole("button", { name: /Open the demo/ }).click();
  await expect(page).toHaveURL(/\/demo$/);
  await expect(page.getByRole("note").filter({ hasText: "Public demo" })).toBeVisible();
}

/** Run one Demo Center workflow and return its result panel. */
export async function runWorkflow(page: Page, title: string) {
  const card = page.locator("section, div").filter({ has: page.getByText(title, { exact: true }) }).filter({ has: page.getByRole("button", { name: "Run" }) }).last();
  await card.getByRole("button", { name: "Run" }).click();
  const result = card.getByRole("status").first();
  await expect(result).toBeVisible({ timeout: 60_000 });
  return { card, result };
}

/** The visitor's API token (to call the API exactly as the page does). */
export const token = (page: Page) => page.evaluate(() => localStorage.getItem("rocky.token"));
