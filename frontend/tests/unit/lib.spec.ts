/** Unit tests for client logic that every device depends on (run by Playwright's runner, no browser). */
import { expect, test } from "@playwright/test";
import { ago, api, ApiError, fmt, pct } from "../../lib/api";
import { parseFrames } from "../../lib/live";

test.describe("live event stream parser", () => {
  test("parses data frames, skips comments and retry fields", () => {
    const { events, rest } = parseFrames('retry: 3000\n: connected\n\ndata: {"type":"task","ts":"1"}\n\n: keepalive\n\ndata: {"type":"approval","ts":"2"}\n\n');
    expect(events.map((e) => e.type)).toEqual(["task", "approval"]);
    expect(rest).toBe("");
  });
  test("keeps an incomplete frame for the next chunk (mobile networks split anywhere)", () => {
    const a = parseFrames('data: {"type":"ta');
    expect(a.events).toEqual([]);
    const b = parseFrames(a.rest + 'sk","ts":"1"}\n\n');
    expect(b.events[0].type).toBe("task");
  });
  test("a malformed frame is skipped, not fatal", () => {
    const { events } = parseFrames('data: {not json\n\ndata: {"type":"ok","ts":"1"}\n\n');
    expect(events.map((e) => e.type)).toEqual(["ok"]);
  });
});

test.describe("api client", () => {
  const realFetch = globalThis.fetch;
  test.afterEach(() => { globalThis.fetch = realFetch; });

  test("calls the same origin by default (works from a phone on the LAN)", async () => {
    let url = "";
    globalThis.fetch = (async (u: string) => { url = u; return new Response("{}", { status: 200 }); }) as typeof fetch;
    await api("/api/system/status");
    expect(url).toBe("/api/system/status");
  });
  test("an unreachable server becomes a clear error, not a TypeError", async () => {
    globalThis.fetch = (async () => { throw new TypeError("Failed to fetch"); }) as typeof fetch;
    const e = await api("/api/x").catch((x) => x);
    expect(e).toBeInstanceOf(ApiError);
    expect(e.status).toBe(0);
    expect(e.message).toContain("Cannot reach the Demonkoncernen server");
  });
  test("reads time out; the message says so", async () => {
    globalThis.fetch = ((_u: string, init: RequestInit) => new Promise((_r, rej) => init.signal?.addEventListener("abort", () => rej(new DOMException("aborted", "AbortError"))))) as typeof fetch;
    const e = await api("/api/slow", { timeoutMs: 50 }).catch((x) => x);
    expect(e.message).toContain("did not answer within");
  });
  test("writes do not time out by default (AI work takes minutes)", async () => {
    let signalTimedOut = false;
    globalThis.fetch = (async (_u: string, init: RequestInit) => { await new Promise((r) => setTimeout(r, 80)); signalTimedOut = !!init.signal?.aborted; return new Response('{"ok":true}'); }) as typeof fetch;
    expect(await api("/api/ai/reason", { method: "POST", json: {} })).toEqual({ ok: true });
    expect(signalTimedOut).toBe(false);
  });
  test("server error detail reaches the user", async () => {
    globalThis.fetch = (async () => new Response(JSON.stringify({ detail: "requires role: admin" }), { status: 403 })) as typeof fetch;
    const e = await api("/api/daemon/settings", { method: "PATCH", json: {} }).catch((x) => x);
    expect([e.status, e.message]).toEqual([403, "requires role: admin"]);
  });
});

test("formatters show a dash for unknown values instead of inventing one", () => {
  expect([pct(null), fmt(undefined), ago(null)]).toEqual(["—", "—", "—"]);
  expect(pct(0.256)).toBe("26%");
  expect(ago(new Date(Date.now() - 90_000).toISOString())).toBe("1m ago");
  expect(ago(new Date(Date.now() + 23.5 * 3600_000).toISOString())).toBe("in 23h"); // an expiry is in the future, not "0s ago"
  expect(ago(new Date(Date.now() + 10 * 60_000).toISOString())).toBe("in 10m");
});
