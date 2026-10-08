// Validation for reference-data fixtures seeded into PostgreSQL (D-020).
import { BlockList, isIP } from "node:net";
import { reputationLevel } from "./schema.ts";

export type ReputationLevel = (typeof reputationLevel.enumValues)[number];

export interface IpReputationRow {
  ip: string;
  reputation: ReputationLevel;
  score: number;
  tags: string[];
  source: string;
}

export interface MitreTechniqueRow {
  techniqueId: string;
  name: string;
  tactics: string[];
  description: string;
  attackVersion: string;
}

export class FixtureError extends Error {}

// Fixtures may only contain synthetic addresses: RFC 1918 private and RFC 5737 documentation ranges.
const SYNTHETIC_RANGES = new BlockList();
for (const [network, prefix] of [
  ["10.0.0.0", 8],
  ["172.16.0.0", 12],
  ["192.168.0.0", 16],
  ["192.0.2.0", 24],
  ["198.51.100.0", 24],
  ["203.0.113.0", 24],
] as const) {
  SYNTHETIC_RANGES.addSubnet(network, prefix, "ipv4");
}

/** True for RFC 1918 / RFC 5737 IPv4 addresses, the only ones fixtures may use (D-032). */
export const isSyntheticIp = (ip: string): boolean => isIP(ip) === 4 && SYNTHETIC_RANGES.check(ip, "ipv4");

const TECHNIQUE_ID = /^T[0-9]{4}(\.[0-9]{3})?$/;

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null && !Array.isArray(value);

const isReputationLevel = (value: string): value is ReputationLevel =>
  (reputationLevel.enumValues as readonly string[]).includes(value);

function requireString(record: Record<string, unknown>, key: string, where: string): string {
  const value = record[key];
  if (typeof value !== "string" || value.trim() === "") {
    throw new FixtureError(`${where}.${key}: expected a non-empty string`);
  }
  return value;
}

function requireStringArray(record: Record<string, unknown>, key: string, where: string, minLength: number): string[] {
  const value = record[key];
  if (!Array.isArray(value) || value.length < minLength || !value.every((v) => typeof v === "string" && v !== "")) {
    throw new FixtureError(`${where}.${key}: expected an array of at least ${minLength} non-empty strings`);
  }
  return value as string[];
}

function requireEntries(raw: unknown, key: string, where: string): unknown[] {
  if (!isRecord(raw) || !Array.isArray(raw[key]) || raw[key].length === 0) {
    throw new FixtureError(`${where}: expected an object with a non-empty "${key}" array`);
  }
  return raw[key];
}

export function parseIpReputationFixture(raw: unknown): IpReputationRow[] {
  const entries = requireEntries(raw, "entries", "ip_reputation");
  const source = requireString(raw as Record<string, unknown>, "source", "ip_reputation");
  const seen = new Set<string>();
  return entries.map((entry, i) => {
    const where = `ip_reputation.entries[${i}]`;
    if (!isRecord(entry)) throw new FixtureError(`${where}: expected an object`);
    const ip = requireString(entry, "ip", where);
    if (!isSyntheticIp(ip)) {
      throw new FixtureError(`${where}.ip: ${ip} is not a synthetic IPv4 address (RFC 1918 / RFC 5737)`);
    }
    if (seen.has(ip)) throw new FixtureError(`${where}.ip: duplicate ${ip}`);
    seen.add(ip);
    const reputation = requireString(entry, "reputation", where);
    if (!isReputationLevel(reputation)) {
      throw new FixtureError(`${where}.reputation: ${reputation} is not one of ${reputationLevel.enumValues.join(", ")}`);
    }
    const score = entry.score;
    if (typeof score !== "number" || !Number.isInteger(score) || score < 0 || score > 100) {
      throw new FixtureError(`${where}.score: expected an integer 0-100`);
    }
    return { ip, reputation, score, tags: requireStringArray(entry, "tags", where, 0), source };
  });
}

export function parseMitreFixture(raw: unknown): MitreTechniqueRow[] {
  const entries = requireEntries(raw, "techniques", "mitre_techniques");
  const attackVersion = requireString(raw as Record<string, unknown>, "attack_version", "mitre_techniques");
  const seen = new Set<string>();
  return entries.map((entry, i) => {
    const where = `mitre_techniques.techniques[${i}]`;
    if (!isRecord(entry)) throw new FixtureError(`${where}: expected an object`);
    const techniqueId = requireString(entry, "technique_id", where);
    if (!TECHNIQUE_ID.test(techniqueId)) throw new FixtureError(`${where}.technique_id: invalid ${techniqueId}`);
    if (seen.has(techniqueId)) throw new FixtureError(`${where}.technique_id: duplicate ${techniqueId}`);
    seen.add(techniqueId);
    return {
      techniqueId,
      name: requireString(entry, "name", where),
      tactics: requireStringArray(entry, "tactics", where, 1),
      description: requireString(entry, "description", where),
      attackVersion,
    };
  });
}
