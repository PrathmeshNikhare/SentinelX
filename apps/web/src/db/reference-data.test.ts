import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { FixtureError, parseIpReputationFixture, parseMitreFixture } from "./reference-data.ts";

const fixture = (name: string): unknown =>
  JSON.parse(readFileSync(new URL(`../../../../fixtures/${name}`, import.meta.url), "utf8"));

const ipFixture = (entries: unknown[]) => ({ source: "test", entries });
const goodIp = { ip: "192.0.2.10", reputation: "unknown", score: 20, tags: [] };
const mitreFixture = (techniques: unknown[]) => ({ attack_version: "test", techniques });
const goodTechnique = { technique_id: "T1110", name: "Brute Force", tactics: ["credential-access"], description: "d" };

describe("parseIpReputationFixture", () => {
  it("accepts the committed fixture", () => {
    const rows = parseIpReputationFixture(fixture("ip_reputation.json"));
    expect(rows.length).toBeGreaterThan(0);
    expect(rows.find((r) => r.ip === "203.0.113.45")?.reputation).toBe("malicious");
  });

  it.each([
    ["a real public address", { ...goodIp, ip: "8.8.8.8" }],
    ["an invalid address", { ...goodIp, ip: "999.1.1.1" }],
    ["IPv6", { ...goodIp, ip: "2001:db8::1" }],
    ["an unknown reputation", { ...goodIp, reputation: "evil" }],
    ["a score above 100", { ...goodIp, score: 101 }],
    ["a fractional score", { ...goodIp, score: 1.5 }],
    ["non-string tags", { ...goodIp, tags: [1] }],
  ])("rejects %s", (_label, entry) => {
    expect(() => parseIpReputationFixture(ipFixture([entry]))).toThrow(FixtureError);
  });

  it("rejects duplicates and empty fixtures", () => {
    expect(() => parseIpReputationFixture(ipFixture([goodIp, goodIp]))).toThrow(/duplicate/);
    expect(() => parseIpReputationFixture(ipFixture([]))).toThrow(FixtureError);
  });
});

describe("parseMitreFixture", () => {
  it("accepts the committed fixture", () => {
    const rows = parseMitreFixture(fixture("mitre_techniques.json"));
    expect(rows.find((r) => r.techniqueId === "T1059.001")?.name).toBe("PowerShell");
  });

  it.each([
    ["a malformed id", { ...goodTechnique, technique_id: "T110" }],
    ["a sub-technique with two digits", { ...goodTechnique, technique_id: "T1110.01" }],
    ["no tactics", { ...goodTechnique, tactics: [] }],
    ["a missing name", { ...goodTechnique, name: "" }],
  ])("rejects %s", (_label, entry) => {
    expect(() => parseMitreFixture(mitreFixture([entry]))).toThrow(FixtureError);
  });

  it("rejects duplicate technique ids", () => {
    expect(() => parseMitreFixture(mitreFixture([goodTechnique, goodTechnique]))).toThrow(/duplicate/);
  });
});
