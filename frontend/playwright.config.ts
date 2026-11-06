import { defineConfig, devices, type Project } from "@playwright/test";
import os from "node:os";
import path from "node:path";

/** One runner for every frontend test:
 *   unit     — plain logic (lib/), no browser
 *   e2e      — real workflows against a real backend, once per device class (desktop, tablet, phone, Android phone)
 *   matrix   — responsive layout at 9 widths + landscape, accessibility (axe), PWA, performance metrics
 *
 * By default the suite starts its OWN stack (scripts/dev.sh --prod) on ports 8100/3100 with a throw-away database, so
 * it never touches your data. Point it at a running instance instead with E2E_BASE_URL (+ E2E_EMAIL / E2E_PASSWORD).
 * Engines: Chromium by default; E2E_ENGINES=chromium,webkit,firefox once those browsers are installed
 * (`npx playwright install webkit firefox`). Emulation is not a physical device — see docs/CROSS_PLATFORM.md.
 */
const WEB_PORT = Number(process.env.E2E_WEB_PORT || 3100);
const API_PORT = Number(process.env.E2E_API_PORT || 8100);
const BASE = process.env.E2E_BASE_URL || `http://127.0.0.1:${WEB_PORT}`;
const ENGINES = (process.env.E2E_ENGINES || "chromium").split(",").map((s) => s.trim()).filter(Boolean) as ("chromium" | "webkit" | "firefox")[];
const DATA = path.join(os.tmpdir(), `dk-e2e-${API_PORT}`);

const device = (name: string, d: (typeof devices)[string], engine: string): Project => {
  const use: Record<string, unknown> = { ...d, browserName: engine };
  if (engine === "firefox") delete use.isMobile; // Firefox has no mobile emulation mode; viewport + touch still apply
  return { name: `${name}-${engine}`, testDir: "./tests/e2e", dependencies: ["setup"], use: { ...use, storageState: "tests/.auth/admin.json" } };
};

export default defineConfig({
  testDir: "./tests",
  timeout: 60_000,
  expect: { timeout: 10_000 },
  workers: 1, // one shared backend: tests change global state (emergency stop), so they run one at a time
  reporter: [["list"], ["html", { open: "never", outputFolder: "playwright-report" }], ["json", { outputFile: "test-results/results.json" }]],
  use: { baseURL: BASE, trace: "retain-on-failure", screenshot: "only-on-failure" },
  webServer: process.env.E2E_BASE_URL ? undefined : {
    command: `rm -rf "${DATA}" && mkdir -p "${DATA}" && bash ../scripts/dev.sh --prod`,
    url: `${BASE}/login`,
    timeout: 420_000,
    reuseExistingServer: !process.env.CI,
    stdout: "pipe",
    env: { API_PORT: String(API_PORT), WEB_PORT: String(WEB_PORT), DATABASE_URL: `sqlite:///${DATA}/e2e.db`, ARCHIVE_DIR: `${DATA}/archive`,
           SECRET_KEY: "e2e-only-secret", DAEMON_PREWARM: "0",
           // the suite opens 27 pages in seconds through one proxy address — far above a person's pace (limit is per client IP)
           API_RATE_PER_MIN: "20000" },
  },
  projects: [
    { name: "unit", testDir: "./tests/unit" },
    { name: "setup", testDir: "./tests", testMatch: /global\.setup\.ts/ },
    ...ENGINES.flatMap((e) => [
      device("desktop", { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } }, e),
      device("tablet", devices["iPad (gen 7)"], e),
      device("phone", devices["iPhone 13"], e),
      device("android", devices["Pixel 7"], e),
    ]),
    { name: "matrix", testDir: "./tests/matrix", dependencies: ["setup"], use: { browserName: "chromium", storageState: "tests/.auth/admin.json" } },
  ],
});
