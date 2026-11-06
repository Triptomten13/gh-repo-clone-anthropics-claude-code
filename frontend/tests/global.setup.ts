import { expect, test as setup } from "@playwright/test";
import fs from "node:fs";

/** Signs in once (creating the administrator on a fresh database) and stores the session for every other test. */
import { ADMIN } from "./helpers";

setup("sign in as administrator", async ({ request, baseURL }) => {
  const status = await (await request.get("/api/auth/status")).json();
  const r = await request.post(status.setup_required ? "/api/auth/setup" : "/api/auth/login", { data: ADMIN });
  expect(r.status(), await r.text()).toBe(200);
  const { token } = await r.json();
  fs.mkdirSync("tests/.auth", { recursive: true });
  fs.writeFileSync("tests/.auth/admin.json", JSON.stringify({ cookies: [], origins: [{ origin: new URL(baseURL!).origin, localStorage: [{ name: "rocky.token", value: token }] }] }));
});
