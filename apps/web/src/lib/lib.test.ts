import { describe, expect, it } from "vitest";
import { hashSessionToken, isSessionTokenFormat, normalizeEmail } from "../server/auth/session-store.ts";
import { formatUtc } from "./format.ts";
import { isIncidentId } from "./ids.ts";

describe("isIncidentId", () => {
  it.each([
    ["inc_3f9a2b1c4d5e6f70", true],
    ["inc_3F9A2B1C4D5E6F70", false],
    ["inc_3f9a2b1c4d5e6f7", false],
    ["se_3f9a2b1c4d5e6f70", false],
    ["inc_3f9a2b1c4d5e6f70' OR 1=1--", false],
    ["", false],
  ])("%s -> %s", (value, expected) => {
    expect(isIncidentId(value)).toBe(expected);
  });
});

describe("formatUtc", () => {
  it("renders UTC regardless of the local time zone", () => {
    expect(formatUtc(new Date("2026-01-01T10:00:00.123Z"))).toBe("2026-01-01 10:00:00Z");
  });
});

describe("session token helpers", () => {
  it("accepts only 43-char base64url tokens", () => {
    expect(isSessionTokenFormat("A".repeat(43))).toBe(true);
    expect(isSessionTokenFormat("A".repeat(42))).toBe(false);
    expect(isSessionTokenFormat(`${"A".repeat(42)}=`)).toBe(false);
    expect(isSessionTokenFormat(`${"A".repeat(42)}'`)).toBe(false);
  });

  it("stores a SHA-256 hex digest, never the token", () => {
    const hash = hashSessionToken("A".repeat(43));
    expect(hash).toMatch(/^[0-9a-f]{64}$/);
    expect(hash).not.toContain("AAAA");
  });

  it("normalizes emails for lookup", () => {
    expect(normalizeEmail("  Analyst@Example.Local ")).toBe("analyst@example.local");
  });
});
