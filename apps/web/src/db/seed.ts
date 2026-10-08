// Syncs reference data from fixtures/ into PostgreSQL (D-020). Rows not in the fixture are removed,
// so the tables always equal the fixtures. Demo events come from the Phase 03 generator, not here (D-032).
import { readFileSync } from "node:fs";
import { inArray, not, sql } from "drizzle-orm";
import type { NodePgDatabase } from "drizzle-orm/node-postgres";
import { parseIpReputationFixture, parseMitreFixture } from "./reference-data.ts";
import { ipReputation, mitreTechniques } from "./schema.ts";

const FIXTURES_DIR = new URL("../../../../fixtures/", import.meta.url);

const readFixture = (name: string): unknown => JSON.parse(readFileSync(new URL(name, FIXTURES_DIR), "utf8"));

export interface SeedCounts {
  ipReputation: number;
  mitreTechniques: number;
}

export async function seedReferenceData(db: NodePgDatabase): Promise<SeedCounts> {
  const ips = parseIpReputationFixture(readFixture("ip_reputation.json"));
  const techniques = parseMitreFixture(readFixture("mitre_techniques.json"));

  await db.transaction(async (tx) => {
    await tx
      .insert(ipReputation)
      .values(ips.map((r) => ({ ip: r.ip, reputation: r.reputation, score: r.score, tagsJson: r.tags, source: r.source })))
      .onConflictDoUpdate({
        target: ipReputation.ip,
        set: {
          reputation: sql`excluded.reputation`,
          score: sql`excluded.score`,
          tagsJson: sql`excluded.tags_json`,
          source: sql`excluded.source`,
          updatedAt: sql`now()`,
        },
      });
    await tx.delete(ipReputation).where(not(inArray(ipReputation.ip, ips.map((r) => r.ip))));

    await tx
      .insert(mitreTechniques)
      .values(
        techniques.map((t) => ({
          techniqueId: t.techniqueId,
          name: t.name,
          tacticsJson: t.tactics,
          description: t.description,
          attackVersion: t.attackVersion,
        })),
      )
      .onConflictDoUpdate({
        target: mitreTechniques.techniqueId,
        set: {
          name: sql`excluded.name`,
          tacticsJson: sql`excluded.tactics_json`,
          description: sql`excluded.description`,
          attackVersion: sql`excluded.attack_version`,
        },
      });
    await tx
      .delete(mitreTechniques)
      .where(not(inArray(mitreTechniques.techniqueId, techniques.map((t) => t.techniqueId))));
  });

  return { ipReputation: ips.length, mitreTechniques: techniques.length };
}
