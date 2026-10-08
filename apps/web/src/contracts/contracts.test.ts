import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { normalizeEvent } from "../ingest/normalize.ts";
import { contractFile, renderSchemas } from "./generate.ts";
import { normalizedEvent, securityEventInput } from "./security-event.ts";

const example = (name: string): unknown => JSON.parse(readFileSync(contractFile(`examples/${name}`), "utf8"));
const valid = {
  event_id: "evt_123",
  timestamp: "2026-01-01T10:00:00Z",
  user_id: "user_1",
  source_ip: "192.0.2.10",
  event_type: "authentication",
  action: "login",
  resource: "portal",
  status: "failed",
};

describe("contract files (D-042)", () => {
  it("contracts/v1/*.schema.json match the zod source (run npm run contracts:generate)", () => {
    for (const [name, content] of Object.entries(renderSchemas())) {
      expect(readFileSync(contractFile(name), "utf8"), name).toBe(content);
    }
  });

  it("the examples satisfy their contracts and normalize into each other", () => {
    const input = securityEventInput.parse(example("security-event.json"));
    const expected = normalizedEvent.parse(example("normalized-event.json"));
    expect(normalizeEvent(input, new Date("2026-01-01T10:00:01Z"))).toEqual({ ok: true, event: expected });
  });
});

describe("securityEventInput", () => {
  it("drops a __proto__ key without polluting any prototype (the API rejects it before zod; see parseJsonBody)", () => {
    const raw = JSON.parse('{"__proto__": {"admin": true}, "ok": 1}') as unknown;
    const result = securityEventInput.safeParse({ ...valid, metadata: raw });
    expect(result.success).toBe(true);
    expect(Object.keys(result.data?.metadata ?? {})).toEqual(["ok"]);
    expect((result.data?.metadata as Record<string, unknown>)["admin"]).toBeUndefined();
    expect(({} as Record<string, unknown>)["admin"]).toBeUndefined();
  });

  it("accepts the docs/14 shape with or without metadata", () => {
    expect(securityEventInput.safeParse(valid).success).toBe(true);
    expect(securityEventInput.safeParse({ ...valid, metadata: { mfa: true, geo: { country: "NL" } } }).success).toBe(true);
    expect(securityEventInput.safeParse({ ...valid, timestamp: "2026-01-01T15:30:00+05:30" }).success).toBe(true);
    expect(securityEventInput.safeParse({ ...valid, source_ip: "2001:db8::1" }).success).toBe(true);
  });

  it.each([
    ["an unknown field", { ...valid, extra: 1 }, "(root)"],
    ["a missing field", { ...valid, status: undefined }, "status"],
    ["a timestamp without offset", { ...valid, timestamp: "2026-01-01T10:00:00" }, "timestamp"],
    ["an invalid IP", { ...valid, source_ip: "999.1.1.1" }, "source_ip"],
    ["an IPv4 with leading zeros", { ...valid, source_ip: "192.0.2.010" }, "source_ip"],
    ["an unknown event type", { ...valid, event_type: "shell" }, "event_type"],
    ["an unknown status", { ...valid, status: "ok" }, "status"],
    ["an event_id with spaces", { ...valid, event_id: "evt 1" }, "event_id"],
    ["an overlong event_id", { ...valid, event_id: "e".repeat(129) }, "event_id"],
    ["a user_id with a slash", { ...valid, user_id: "a/b" }, "user_id"],
    ["a resource with a newline", { ...valid, resource: "portal\nX-Injected: 1" }, "resource"],
    ["an empty resource", { ...valid, resource: "" }, "resource"],
    ["array metadata", { ...valid, metadata: [] }, "metadata"],
    ["a constructor metadata key", { ...valid, metadata: { constructor: "x" } }, "metadata.constructor"],
    ["oversized metadata", { ...valid, metadata: { blob: "x".repeat(5000) } }, "metadata"],
  ])("rejects %s", (_label, body, path) => {
    const result = securityEventInput.safeParse(body);
    expect(result.success).toBe(false);
    const paths = result.error?.issues.map((i) => i.path.map(String).join(".") || "(root)") ?? [];
    expect(paths).toContain(path);
  });
});
