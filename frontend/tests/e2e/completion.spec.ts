import { expect, test, type Page } from "@playwright/test";
import { openShell } from "../helpers";

// Journeys that only existed in the API before the completion round (docs/COMPLETION_AUDIT.md §2.1).

async function adminApi(page: Page) {
  const token = await page.evaluate(() => localStorage.getItem("rocky.token"));
  return { Authorization: `Bearer ${token}` };
}

/** A second person who may decide approvals (four eyes): created by the admin, signed in through the API. */
async function approverHeaders(page: Page) {
  const h = await adminApi(page);
  const email = "e2e-approver@example.com", password = "approver-password-0123";
  await page.request.post("/api/auth/users", { headers: h, data: { email, password, role: "approver" } }); // 409 when it exists
  const r = await page.request.post("/api/auth/login", { data: { email, password } });
  return { Authorization: `Bearer ${(await r.json()).token}` };
}

test("a proposed rule is filed for approval, approved by someone else, and applied from the page that proposed it", async ({ page }) => {
  await openShell(page, "/governance#policies");
  const key = `e2e.rule.${Date.now() % 100000}`;
  await page.getByLabel("Key").fill(key);
  await page.getByLabel(/Action/).fill("tool:email.send.EXECUTE");
  await page.getByRole("button", { name: "Propose" }).click();
  const filed = page.getByRole("status").filter({ hasText: /Filed as approval/ });
  await expect(filed).toBeVisible();
  const id = Number((await filed.getByRole("link").textContent())!.replace("#", ""));

  // applying before approval changes nothing and says why
  await filed.getByRole("button", { name: "Apply once approved" }).click();
  await expect(filed.getByText(/not approved/)).toBeVisible();

  const approver = await approverHeaders(page);
  expect((await page.request.post(`/api/approvals/${id}/decide`, { headers: approver, data: { approve: true } })).ok()).toBeTruthy();
  await filed.getByRole("button", { name: "Apply once approved" }).click();
  await expect(page.getByText(`Applied with approval #${id}.`)).toBeVisible();
  await expect(page.getByRole("cell", { name: new RegExp(`^${key.replaceAll(".", "\\.")}@`) })).toBeVisible();

  // the rule's history is one click away
  await page.getByRole("row", { name: new RegExp(key.replaceAll(".", "\\.")) }).getByRole("button", { name: "History" }).click();
  await expect(page.getByText(`History of ${key}`)).toBeVisible();

  // the approval links back from the Approval Center, and shows that it has been used
  await openShell(page, `/approvals?id=${id}`);
  const row = page.locator(`#approval-${id}`);
  await expect(row).toBeVisible();
  await expect(row.getByText(/used/)).toBeVisible();
  await expect(row.getByRole("link", { name: "Policies" })).toHaveAttribute("href", "/governance#policies");
});

test("Approval Center: delegate a waiting request to another approver, then revoke it", async ({ page }) => {
  await openShell(page, "/approvals");
  await approverHeaders(page); // there must be someone to delegate to
  const h = await adminApi(page);
  const doc = await (await page.request.post("/api/archive/text", { headers: h, data: { title: "e2e lifecycle", text: "to be deleted with approval", evidence_class: "primary_source" } })).json();
  const filed = await (await page.request.post("/api/tools/archive.delete/invoke", { headers: h, data: { args: { document_id: doc.id } } })).json();
  await openShell(page, `/approvals?id=${filed.approval_id}`);
  const row = page.locator(`#approval-${filed.approval_id}`);
  await row.getByLabel(`Delegate approval ${filed.approval_id} to`).selectOption("e2e-approver@example.com");
  await row.getByRole("button", { name: "Delegate" }).click();
  await expect(row.getByText("delegated to e2e-approver@example.com")).toBeVisible();
  await row.getByRole("button", { name: "Revoke" }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByRole("textbox").fill("no longer needed");
  await dialog.getByRole("button", { name: "Revoke" }).click();
  await expect(row.getByText(/revoked by/)).toBeVisible();
});

test("Finance: record a real ledger entry and see it counted", async ({ page }) => {
  await openShell(page, "/finance");
  await page.getByRole("button", { name: "Record an entry" }).click();
  await page.getByLabel("Amount (SEK, positive)").fill("1234");
  await page.getByLabel("Reference").fill("e2e-order-1");
  await page.getByRole("button", { name: "Save entry" }).click();
  await expect(page.getByText(/Recorded revenue .* as entry #\d+\./)).toBeVisible();
  await expect(page.getByRole("link", { name: /Import many/ })).toHaveAttribute("href", "/lab?import=ledger");
});

test("Archive: collections and per-document access are managed where the documents are", async ({ page }) => {
  await openShell(page, "/knowledge#documents");
  await expect(page.getByText(/Collections \(access is inherited/)).toBeVisible();
  const name = `e2e-col-${Date.now() % 100000}`;
  await page.getByLabel("Name (a-z, 0-9, . _ -)").fill(name);
  await page.getByRole("button", { name: "Create / update" }).click();
  await expect(page.getByRole("cell", { name }).first()).toBeVisible();
});
