import { defineConfig, devices } from "@playwright/test";
import os from "node:os";
import path from "node:path";

/** PUBLIC DEMO test suite — verifies a public demo server without touching any other data.
 *
 *   npm run test:demo                       starts its OWN demo stack (DEMO_MODE=1, throw-away DB, ports 8200/3200)
 *   DEMO_BASE_URL=https://demo.example npm run test:demo   checks a deployed public demo instead (read-mostly: it
 *                                           creates one or two visitor sessions and runs sample workflows, as a visitor would)
 *
 * Results: list output, test-results/demo-results.json, and a PASS/FAIL table in test-results/demo-report.md
 * (scripts/demo-report.mjs runs after the suite).
 */
const WEB_PORT = Number(process.env.DEMO_WEB_PORT || 3200);
const API_PORT = Number(process.env.DEMO_API_PORT || 8200);
const BASE = process.env.DEMO_BASE_URL || `http://127.0.0.1:${WEB_PORT}`;
const DATA = path.join(os.tmpdir(), `dk-demo-${API_PORT}`);

export default defineConfig({
  testDir: "./tests/demo",
  timeout: 90_000,
  expect: { timeout: 15_000 },
  workers: 1,
  reporter: [["list"], ["json", { outputFile: "test-results/demo-results.json" }]],
  use: { baseURL: BASE, trace: "retain-on-failure", screenshot: "only-on-failure" },
  projects: [
    { name: "demo-desktop", use: { ...devices["Desktop Chrome"] }, testIgnore: /mobile\.spec/ },
    { name: "demo-phone", use: { ...devices["Pixel 7"] }, testMatch: /mobile\.spec/ },
  ],
  webServer: process.env.DEMO_BASE_URL ? undefined : {
    command: `rm -rf "${DATA}" && mkdir -p "${DATA}" && bash ../scripts/dev.sh --prod`,
    url: `${BASE}/login`,
    timeout: 420_000,
    reuseExistingServer: false,
    stdout: "pipe",
    env: { DEMO_MODE: "1", API_PORT: String(API_PORT), WEB_PORT: String(WEB_PORT), DATABASE_URL: `sqlite:///${DATA}/demo.db`,
           ARCHIVE_DIR: `${DATA}/archive`, SECRET_KEY: "demo-test-only-secret", DAEMON_PREWARM: "0",
           // every test visitor comes from 127.0.0.1 through the web server's proxy
           DEMO_SESSIONS_PER_CLIENT_HOUR: "200", API_RATE_PER_MIN: "20000" },
  },
});
