import { describe, expect, it } from "vitest";
import { normalizedEvent, securityEventInput, type SecurityEventInput } from "../contracts/security-event.ts";
import { parseJsonBody, readBodyLimited } from "./body.ts";
import { parseBrokers, toKafkaMessage } from "./kafka.ts";
import { canonicalIp, MAX_FUTURE_SKEW_MS, normalizeEvent } from "./normalize.ts";
import { bearerToken, checkIngestToken } from "./token.ts";

const NOW = new Date("2026-03-01T12:00:00Z");
const input = (overrides: Partial<SecurityEventInput> = {}): SecurityEventInput =>
  securityEventInput.parse({
    event_id: "evt_1",
    timestamp: "2026-03-01T17:30:00+05:30",
    user_id: "Alice",
    source_ip: "2001:DB8:0:0:0:0:0:1",
    event_type: "authentication",
    action: "Login",
    resource: "  vpn-portal  ",
    status: "failed",
    ...overrides,
  });

describe("normalizeEvent (D-043)", () => {
  it("produces a contract-valid message: UTC time, lowercase identity and action, canonical IP, trimmed resource", () => {
    const result = normalizeEvent(input(), NOW);
    if (!result.ok) throw new Error("expected ok");
    expect(result.event).toEqual({
      schema_version: "v1",
      event_id: "evt_1",
      occurred_at: "2026-03-01T12:00:00.000Z",
      ingested_at: "2026-03-01T12:00:00.000Z",
      user_id: "alice",
      source_ip: "2001:db8::1",
      event_type: "authentication",
      action: "login",
      resource: "vpn-portal",
      status: "failed",
      metadata: {},
    });
    expect(normalizedEvent.safeParse(result.event).success).toBe(true);
  });

  it("allows small clock skew but rejects timestamps more than 5 minutes ahead", () => {
    const at = (ms: number) => input({ timestamp: new Date(NOW.getTime() + ms).toISOString() });
    expect(normalizeEvent(at(MAX_FUTURE_SKEW_MS), NOW).ok).toBe(true);
    expect(normalizeEvent(at(MAX_FUTURE_SKEW_MS + 1000), NOW)).toEqual({
      ok: false,
      issues: [{ path: "timestamp", message: "must not be more than 5 minutes in the future" }],
    });
  });

  it.each([
    ["192.0.2.10", "192.0.2.10"],
    ["2001:DB8::0001", "2001:db8::1"],
    ["2001:db8:0:0:1:0:0:1", "2001:db8::1:0:0:1"],
    ["::ffff:c000:20a", "192.0.2.10"],
  ])("canonicalIp(%s) = %s", (ip, expected) => {
    expect(canonicalIp(ip)).toBe(expected);
  });
});

describe("toKafkaMessage", () => {
  it("keys by user_id and labels the schema version", () => {
    const result = normalizeEvent(input(), NOW);
    if (!result.ok) throw new Error("expected ok");
    const message = toKafkaMessage(result.event);
    expect(message.key).toBe("alice");
    expect(message.headers).toEqual({ "schema-version": "v1", "content-type": "application/json" });
    expect(JSON.parse(message.value)).toEqual(result.event);
  });

  it("parses the broker list", () => {
    expect(parseBrokers(" localhost:9092 , kafka:29092 ")).toEqual(["localhost:9092", "kafka:29092"]);
    expect(() => parseBrokers("")).toThrow(/KAFKA_BROKERS/);
  });
});

describe("ingest token (D-041)", () => {
  const configured = "t".repeat(40);
  it("accepts only the exact configured token", () => {
    expect(checkIngestToken(configured, configured)).toBe("valid");
    expect(checkIngestToken(`${configured}x`, configured)).toBe("invalid");
    expect(checkIngestToken("", configured)).toBe("invalid");
  });

  it("is disabled when unset and refused when too short", () => {
    expect(checkIngestToken(configured, undefined)).toBe("disabled");
    expect(checkIngestToken(configured, "")).toBe("disabled");
    expect(checkIngestToken("short", "short")).toBe("misconfigured");
  });

  it("extracts only well-formed Bearer headers", () => {
    expect(bearerToken("Bearer abc.DEF-123")).toBe("abc.DEF-123");
    expect(bearerToken("bearer abc")).toBeNull();
    expect(bearerToken("Basic abc")).toBeNull();
    expect(bearerToken("Bearer a b")).toBeNull();
    expect(bearerToken(null)).toBeNull();
  });
});

describe("readBodyLimited", () => {
  const streamed = (bytes: number) =>
    new Request("http://x/", {
      method: "POST",
      body: new ReadableStream({
        start(controller) {
          for (let sent = 0; sent < bytes; sent += 1024) controller.enqueue(new Uint8Array(Math.min(1024, bytes - sent)));
          controller.close();
        },
      }),
      // @ts-expect-error -- Node's fetch requires duplex for streaming request bodies
      duplex: "half",
    });

  it("returns the text within the limit", async () => {
    expect(await readBodyLimited(new Request("http://x/", { method: "POST", body: '{"a":1}' }), 100)).toEqual({
      ok: true,
      text: '{"a":1}',
    });
  });

  it("rejects by declared length and by streamed length without Content-Length", async () => {
    const declared = new Request("http://x/", { method: "POST", body: "x".repeat(200) });
    expect(await readBodyLimited(declared, 100)).toEqual({ ok: false, reason: "too_large" });
    expect(await readBodyLimited(streamed(5000), 4096)).toEqual({ ok: false, reason: "too_large" });
    expect((await readBodyLimited(streamed(4096), 4096)).ok).toBe(true);
  });
});

describe("parseJsonBody", () => {
  it("parses JSON and rejects __proto__ keys at any depth", () => {
    expect(parseJsonBody('{"a":{"b":1}}')).toEqual({ ok: true, value: { a: { b: 1 } } });
    expect(parseJsonBody('{"__proto__":{"x":1}}')).toEqual({ ok: false, reason: "forbidden_key" });
    expect(parseJsonBody('{"metadata":{"nested":{"__proto__":1}}}')).toEqual({ ok: false, reason: "forbidden_key" });
    expect(parseJsonBody("{not json")).toEqual({ ok: false, reason: "invalid_json" });
  });
});
