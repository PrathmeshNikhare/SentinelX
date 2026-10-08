import { describe, expect, it } from "vitest";
import { defaultBase, expandScenario, loadScenario, parseScenario, SCENARIO_IDS, sendEvents } from "./scenarios.ts";

const BASE = new Date("2026-01-01T10:00:00Z");

describe("demo scenarios (D-044)", () => {
  it.each(SCENARIO_IDS)("scenario %s loads, validates and expands deterministically", (id) => {
    const scenario = loadScenario(id);
    const first = expandScenario(scenario, BASE);
    expect(first).toEqual(expandScenario(scenario, BASE));
    expect(first[0]?.event_id).toBe(`demo-${id.toLowerCase()}-20260101T100000Z-01`);
    expect(new Set(first.map((e) => e.event_id)).size).toBe(first.length);
    expect(first[0]?.timestamp).toBe("2026-01-01T10:00:00.000Z");
  });

  it("scenario A follows docs/12: five failures, a success, PowerShell, sensitive file reads", () => {
    const events = expandScenario(loadScenario("A"), BASE);
    expect(events.slice(0, 5).every((e) => e.event_type === "authentication" && e.status === "failed")).toBe(true);
    expect(events[5]).toMatchObject({ event_type: "authentication", status: "success" });
    expect(events.some((e) => e.event_type === "process" && e.resource === "powershell.exe")).toBe(true);
    expect(events.filter((e) => e.event_type === "file_access").length).toBeGreaterThanOrEqual(1);
  });

  it("defaults the base so the last event lands at now (whole seconds)", () => {
    const scenario = loadScenario("A");
    const now = new Date("2026-10-08T12:00:00.789Z");
    const events = expandScenario(scenario, defaultBase(scenario, now));
    expect(events.at(-1)?.timestamp).toBe("2026-10-08T12:00:00.000Z");
  });

  it("rejects fixtures with real public IPs or unordered offsets", () => {
    const event = {
      offset_seconds: 0,
      user_id: "u",
      source_ip: "8.8.8.8",
      event_type: "authentication",
      action: "login",
      resource: "r",
      status: "success",
    };
    const file = { id: "A", name: "n", description: "d", expected: "e", events: [event] };
    expect(() => parseScenario(file)).toThrow(/RFC 1918/);
    const ok = { ...event, source_ip: "192.0.2.1" };
    expect(() => parseScenario({ ...file, events: [{ ...ok, offset_seconds: 10 }, ok] })).toThrow(/ordered/);
  });

  it("sends with the bearer token and stops at the first rejection", async () => {
    const calls: { auth: string | null; body: string }[] = [];
    const fakeFetch = (async (_url: URL, init?: RequestInit) => {
      const headers = new Headers(init?.headers);
      calls.push({ auth: headers.get("authorization"), body: String(init?.body) });
      return Response.json({ error: "x" }, { status: calls.length === 2 ? 400 : 202 });
    }) as typeof fetch;
    const events = expandScenario(loadScenario("B"), BASE);
    const results = await sendEvents("http://localhost:3000", "tok", events, fakeFetch);
    expect(results.map((r) => r.status)).toEqual([202, 400]);
    expect(calls[0]?.auth).toBe("Bearer tok");
    expect(JSON.parse(calls[0]?.body ?? "{}")).toEqual(events[0]);
  });
});
