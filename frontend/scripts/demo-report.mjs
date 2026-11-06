// PASS / FAIL report for the public demo suite: reads test-results/demo-results.json (Playwright JSON reporter) and
// writes test-results/demo-report.md. Exit code 1 if any scenario failed or nothing ran — a report never hides a failure.
import fs from "node:fs";

const src = "test-results/demo-results.json";
if (!fs.existsSync(src)) { console.error(`✗ ${src} not found — did the suite run?`); process.exit(1); }
const json = JSON.parse(fs.readFileSync(src, "utf8"));
const rows = [];
const walk = (suite, file) => {
  for (const s of suite.suites ?? []) walk(s, s.file ?? file);
  for (const spec of suite.specs ?? []) {
    for (const t of spec.tests ?? []) {
      const last = t.results?.[t.results.length - 1];
      const status = t.status === "skipped" ? "SKIP" : t.status === "expected" ? "PASS" : t.status === "flaky" ? "PASS (flaky)" : "FAIL";
      const err = last?.error?.message?.split("\n")[0]?.replace(/\u001b\[[0-9;]*m/g, "").slice(0, 160) ?? "";
      rows.push({ name: spec.title, project: t.projectName, status, ms: last?.duration ?? 0, err });
    }
  }
};
walk(json);
const failed = rows.filter((r) => r.status === "FAIL").length;
const when = json.stats?.startTime ?? new Date().toISOString();
const target = process.env.DEMO_BASE_URL || "local demo stack (DEMO_MODE=1, throw-away database)";
const md = [
  `# Public demo test report`, ``,
  `- When: ${when}`, `- Target: ${target}`,
  `- Result: **${failed || !rows.length ? "FAIL" : "PASS"}** — ${rows.filter((r) => r.status.startsWith("PASS")).length} passed, ${failed} failed, ${rows.filter((r) => r.status === "SKIP").length} skipped`,
  `- Browser: Chromium (desktop, and Pixel 7 emulation for the mobile scenario) — emulation is not a physical device`, ``,
  `| Scenario | Device | Result | Time | Failure |`, `|---|---|---|---|---|`,
  ...rows.map((r) => `| ${r.name} | ${r.project.replace("demo-", "")} | ${r.status} | ${(r.ms / 1000).toFixed(1)} s | ${r.err.replace(/\|/g, "\\|")} |`), ``,
].join("\n");
fs.writeFileSync("test-results/demo-report.md", md);
console.log(md);
process.exit(failed || !rows.length ? 1 : 0);
