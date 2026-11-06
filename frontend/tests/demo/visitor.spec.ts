/** Public demo: what an anonymous visitor can do — and what the backend refuses. Each test is one scenario of the
 *  PASS/FAIL report (test-results/demo-report.md). */
import { expect, test } from "@playwright/test";
import { runWorkflow, startDemo, token } from "./helpers";

test("anonymous visitor: landing page, honest feature list, public status", async ({ page, request }) => {
  await page.goto("/");
  await expect(page).toHaveURL(/\/welcome$/);
  await expect(page.getByRole("heading", { name: "What works on this server" })).toBeVisible();
  await expect(page.getByText("Model-backed chat and drafting")).toBeVisible();
  await page.getByRole("link", { name: "System status" }).first().click();
  await expect(page.getByRole("heading", { name: "All core services operational" })).toBeVisible();
  const st = await (await request.get("/api/status")).json();
  expect(st.environment).toBe("public-demo");
  for (const p of ["/health", "/ready", "/api/version"]) expect((await request.get(p)).status(), p).toBe(200);
  // nobody can claim the administrator account through the browser
  expect((await request.post("/api/auth/setup", { data: { email: "attacker@example.com", password: "correct-horse-battery" } })).status()).toBe(403);
});

test("demo session: temporary visitor account with least privilege", async ({ page }) => {
  await startDemo(page);
  const t = await token(page);
  const me = await page.request.get("/api/auth/me", { headers: { Authorization: `Bearer ${t}` } });
  const body = await me.json();
  expect(body.role).toBe("demo");
  expect(body.email).toMatch(/@demo\.invalid$/);
  expect(body.permissions).not.toContain("approval.decide");
  expect(body.permissions).not.toContain("tools.invoke");
  await expect(page.getByText(/action\(s\) left in this session/)).toBeVisible();
});

test("sample agent execution: G-sus delegates to real agents and verifies", async ({ page }) => {
  await startDemo(page);
  const { result } = await runWorkflow(page, "Evaluate a sample product");
  await expect(result.getByText("completed").first()).toBeVisible();
  await expect(result.getByText("RULE-BASED · NO AI MODEL")).toBeVisible();
  await result.getByRole("link", { name: /Trace & replay/ }).click();
  await expect(page.getByText("not a re-execution")).toBeVisible();
  await expect(page.getByText(/child runs:/)).toBeVisible();
});

test("sample workflow execution: grounded answer from the sample Knowledge Vault", async ({ page }) => {
  await startDemo(page);
  const { result } = await runWorkflow(page, "Ask the sample Knowledge Vault");
  await expect(result.getByText("completed").first()).toBeVisible();
  await expect(result.getByText(/cited passage/)).toBeVisible();
  const { result: r2 } = await runWorkflow(page, "Deterministic answer (no model)");
  await expect(r2.getByText(/Answer: 120/)).toBeVisible();
});

test("approval-required workflow: the run stops and the visitor cannot approve", async ({ page }) => {
  await startDemo(page);
  const { card, result } = await runWorkflow(page, "Request a product launch (needs a human)");
  await expect(result.getByText("waiting for approval").first()).toBeVisible();
  await card.getByRole("button", { name: "Try to approve it yourself" }).click();
  await expect(card.getByText(/Approval refused by the backend: .*approval\.decide/)).toBeVisible();
});

test("permission denied: tools, uploads, settings and admin pages are refused", async ({ page }) => {
  await startDemo(page);
  const { result } = await runWorkflow(page, "Use a tool without a grant");
  await expect(result.getByText(/Refused by the backend, as it must be: .*tools\.invoke/)).toBeVisible();
  const h = { Authorization: `Bearer ${await token(page)}` };
  expect((await page.request.post("/api/archive/text", { headers: h, data: { title: "x", text: "y" } })).status()).toBe(403);
  expect((await page.request.patch("/api/daemon/settings", { headers: h, data: { offline_mode: false } })).status()).toBe(403);
  expect((await page.request.get("/api/auth/users", { headers: h })).status()).toBe(403);
  expect((await page.request.post("/api/gsus/runs", { headers: h, data: { objective: "Buy ads for every product" } })).status()).toBe(403);
  // a page that needs more rights explains itself instead of failing silently
  await page.goto("/daemon");
  await page.getByRole("button", { name: "Providers & keys" }).click();
  await expect(page.getByText(/Not available in the public demo \(requires role: admin\)/)).toBeVisible();
});

test("knowledge retrieval: restricted documents never reach a visitor", async ({ page }) => {
  await startDemo(page);
  const h = { Authorization: `Bearer ${await token(page)}` };
  const r = await (await page.request.post("/api/archive/search", { headers: h, data: { query: "LANTERN-RESTRICTED-7 approvals", k: 10 } })).json();
  const titles = r.results.map((x: { title: string }) => x.title);
  expect(titles).toContain("How consequential actions are approved");
  expect(titles).not.toContain("Restricted memo (synthetic sample)");
});

test("audit record creation: the visitor's actions are in the audit trail", async ({ page }) => {
  await startDemo(page);
  await runWorkflow(page, "Deterministic answer (no model)");
  const h = { Authorization: `Bearer ${await token(page)}` };
  const me = (await (await page.request.get("/api/auth/me", { headers: h })).json()).email;
  const recs = await (await page.request.get("/api/audit/records?limit=500", { headers: h })).json();
  expect(recs.some((x: { actor: string; action: string }) => x.actor === me && x.action === "demo.session")).toBe(true);
  await page.goto("/governance#audit");
  await expect(page.getByText("demo.session").first()).toBeVisible();
});

test("backend failure: the interface says so and offers recovery", async ({ page }) => {
  await startDemo(page);
  await page.route("**/api/**", (route) => route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ detail: "service unavailable" }) }));
  await page.goto("/demo");
  await expect(page.getByText("service unavailable").first()).toBeVisible();
  await page.goto("/status");
  await expect(page.getByText(/The backend did not answer/)).toBeVisible();
  await page.unroute("**/api/**");
  await page.getByRole("button", { name: "Check again" }).click();
  await expect(page.getByRole("heading", { name: "All core services operational" })).toBeVisible();
});
