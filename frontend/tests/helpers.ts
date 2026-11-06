import { expect, type Page } from "@playwright/test";

export const ADMIN = { email: process.env.E2E_EMAIL || "e2e-admin@example.com", password: process.env.E2E_PASSWORD || "e2e-password-0123" };

/** Phones and portrait tablets get the bottom tab bar; ≥ 1024 px the sidebar. */
export const isCompact = (page: Page) => (page.viewportSize()?.width ?? 1440) < 1024;

export async function openShell(page: Page, path = "/") {
  await page.goto(path);
  await expect(page.locator("#main")).toBeVisible();
}

/** Every page in the navigation (the shell routes). */
export const ROUTES = ["/", "/agents", "/ai", "/approvals", "/archive", "/archivum", "/chamber", "/control", "/daemon", "/experiments", "/field",
  "/finance", "/flare", "/flare/brands", "/flare/campaigns", "/flare/collab", "/flare/mutations", "/flare/personas", "/flare/portfolio",
  "/flare/sideways", "/governance", "/hq", "/knowledge", "/lab", "/portfolio", "/radar", "/research", "/settings"];
