import { expect, test, type Page } from "@playwright/test";
import { openShell } from "../helpers";

// Astral personnel, The Bestiary and the Custom Agent Creator, on every device project (desktop, tablet, phone,
// Android). The test stack has no language model, so AI buttons use the creator's labelled rules fallback.

const unique = (base: string) => `${base} ${Date.now().toString(36).slice(-5)}`;

async function archive(page: Page, id: string) {
  const r = await page.request.post(`/api/personnel/agents/${id}/lifecycle`, {
    data: { action: "archive" },
    headers: { Authorization: `Bearer ${await page.evaluate(() => localStorage.getItem("rocky.token"))}` },
  });
  expect(r.ok()).toBeTruthy();
}

test("one register for every race: name · race · specialization, filters narrow without grouping by race", async ({ page }) => {
  await openShell(page, "/personnel");
  await expect(page.getByRole("link", { name: "Malphas · Demon · Model Hunting" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Sentinel · Sasquatch · System Monitoring" })).toBeVisible();
  await page.getByLabel("Race").selectOption("leprechaun");
  await expect(page.getByTestId("agent-card")).toHaveCount(1);
  await expect(page.getByRole("link", { name: /^Lucky · Leprechaun/ })).toBeVisible();
  await page.getByRole("button", { name: "Clear filters" }).click();
  await page.getByLabel("Department").selectOption("security_governance");
  await expect(page.getByRole("link", { name: /Grimwald · Griffin/ })).toBeVisible();
  await expect(page.getByRole("link", { name: /Kverulant · Spirit/ })).toBeVisible();   // different races, one department
  await page.getByRole("tab", { name: "Chain of command" }).click();
  await expect(page.getByRole("list", { name: "Chain of command" }).getByRole("link", { name: /^G-SUS/ })).toBeVisible();
  await page.getByRole("tab", { name: "Departments" }).click();
  await expect(page.getByText("No agents yet.").first()).toBeVisible();                  // honest empty departments
});

test("profile → Bestiary article → agents of that race → creator with the race preselected", async ({ page }) => {
  await openShell(page, "/personnel/perf_engineer");
  await expect(page.getByRole("heading", { name: "Sentinel · Sasquatch · System Monitoring" })).toBeVisible();
  for (const section of ["1 · Identity & personality", "8 · Permissions & limits", "13 · Relationships"]) await expect(page.getByText(section)).toBeVisible();
  await expect(page.getByText(/grant nothing/).first()).toBeVisible();
  await page.getByRole("link", { name: "Sasquatch", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Sasquatch" })).toBeVisible();
  await expect(page.getByText(/Not scientifically verified/)).toBeVisible();
  await expect(page.getByRole("link", { name: "Sentinel · Sasquatch · System Monitoring" })).toBeVisible();
  await page.getByTestId("create-from-species").click();
  await expect(page.getByRole("heading", { name: "Custom Agent Creator" })).toBeVisible();
  await expect(page.getByTestId("preview-display")).toContainText("Sasquatch");
});

test("The Bestiary searches alternative names and keeps folklore, fiction and canon apart", async ({ page }) => {
  await openShell(page, "/bestiary");
  await page.getByLabel("Search names and alternative names").fill("bean sí");
  await expect(page.getByTestId("being-card")).toHaveCount(1);
  await page.getByRole("link", { name: "Banshee" }).click();
  await expect(page.getByText("Traditional belief")).toBeVisible();
  await expect(page.getByText("Sources — further reading")).toBeVisible();
  await openShell(page, "/bestiary/yokai");
  await expect(page.getByText(/broad category/).first()).toBeVisible();
  await openShell(page, "/bestiary?tab=specializations");
  await expect(page.getByRole("heading", { name: "Botanical Intelligence" })).toBeVisible();
  await expect(page.getByText(/never locked to a race/)).toBeVisible();
});

test("Agent Creator: design, edit the preview, review, create — the agent becomes ACTIVE only after its checks", async ({ page }) => {
  test.setTimeout(120_000);
  await page.goto("/personnel/create?species=fairy&source=BESTIARY");
  await page.getByRole("button", { name: "Start over" }).click();
  await page.goto("/personnel/create?species=fairy&source=BESTIARY");
  await page.getByLabel("Describe the idea in your own words").fill("Skapa en fairy som är specialist på växter, botanik och trädgårdsodling.");
  await page.getByRole("button", { name: "Design entire agent" }).click();
  await expect(page.getByText(/Assembled by deterministic rules|Designed by AI/)).toBeVisible({ timeout: 30_000 });
  await page.getByTestId("design-proposals").getByRole("button", { name: "Use this proposal" }).first().click();
  const name = unique("Bryony");
  await page.getByLabel("Name", { exact: true }).fill(name);
  await expect(page.getByTestId("preview-display")).toContainText(`${name} · Fairy · Botanical Intelligence`, { timeout: 15_000 });
  await page.getByRole("button", { name: /Review$/ }).click();
  await expect(page.getByText("The profile is valid.")).toBeVisible({ timeout: 15_000 });
  const dup = page.getByRole("group", { name: /Existing agents cover similar ground/ });
  if (await dup.count()) await dup.getByLabel("Create a completely new agent").check();
  await page.getByRole("button", { name: /Create Agent$/ }).click();
  await page.getByRole("checkbox").check();
  await page.getByRole("button", { name: "Create agent", exact: true }).click();
  const result = page.getByTestId("create-result");
  await expect(result.getByRole("status").first()).toContainText("ACTIVE", { timeout: 30_000 });
  await expect(result.getByText("Pipeline — 22 steps")).toBeVisible();
  await expect(result.getByText(/behaviour/).first()).toBeVisible();                   // behavioural checks: skipped, not passed
  await result.getByRole("link", { name: /profile/ }).click();
  await expect(page.getByRole("heading", { name: `${name} · Fairy · Botanical Intelligence` })).toBeVisible();
  await archive(page, page.url().split("/").pop()!);
});

test("Agent Creator: problems block creation and the work survives a reload", async ({ page }) => {
  await page.goto("/personnel/create?source=PERSONNEL");
  await page.getByRole("button", { name: "Start over" }).click();
  await page.getByLabel("Title or alias").fill("Night Watch");
  await page.reload();
  await expect(page.getByLabel("Title or alias")).toHaveValue("Night Watch");          // restored from this browser
  await page.getByRole("button", { name: /Review$/ }).click();
  await expect(page.getByText(/problem\(s\) to fix/)).toBeVisible({ timeout: 15_000 });
  await expect(page.getByRole("button", { name: "persona_name" })).toBeVisible();
  await page.getByRole("button", { name: /Create Agent$/ }).click();
  await page.getByRole("checkbox").check();
  await expect(page.getByRole("button", { name: "Create agent", exact: true })).toBeDisabled();
  await page.getByRole("button", { name: "Start over" }).click();
});

test("G-SUS proposes an agent in chat; nothing is created until approved, and Cancel dismisses it", async ({ page }) => {
  await openShell(page, "/chamber");
  await page.locator("#objective").fill("Skapa en fairy som är specialist på växter, botanik och trädgårdsodling.");
  await page.getByRole("button", { name: "Ask G-sus" }).click();
  const card = page.getByTestId("proposal-card");
  await expect(card).toBeVisible({ timeout: 60_000 });
  await expect(card.getByLabel("Species")).toHaveValue("fairy");
  await expect(page.getByText(/Inget är skapat ännu/)).toBeVisible();
  await card.getByRole("button", { name: "Cancel" }).click();
  await expect(page.getByText("Proposal dismissed — nothing was created.")).toBeVisible();
});
