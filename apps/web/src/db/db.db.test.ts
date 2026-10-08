// Phase 01 integration: clean migration from an empty database, CRUD and constraints, reference seeds,
// and role permissions (D-022, D-031). Runs against a throwaway database created and dropped here.
import { readFileSync } from "node:fs";
import { eq, sql } from "drizzle-orm";
import { drizzle, type NodePgDatabase } from "drizzle-orm/node-postgres";
import pg from "pg";
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { authenticate, createSession, findActiveSession, revokeSession, SESSION_TTL_MS } from "../server/auth/session-store.ts";
import { createAnalyst } from "./admin.ts";
import { databaseUrl } from "./env.ts";
import { MIGRATIONS_FOLDER, runMigrations } from "./migrate.ts";
import {
  alerts,
  detectionSignals,
  evidence,
  incidentAlerts,
  incidentEvents,
  incidents,
  investigationRuns,
  investigationTrace,
  ipReputation,
  mitreTechniques,
  securityEvents,
} from "./schema.ts";
import { seedReferenceData } from "./seed.ts";

const EXPECTED_TABLES = [
  "alerts",
  "analyst_sessions",
  "analysts",
  "detection_signals",
  "evidence",
  "incident_alerts",
  "incident_events",
  "incidents",
  "investigation_runs",
  "investigation_trace",
  "ip_reputation",
  "knowledge_documents",
  "mitre_techniques",
  "security_events",
];
const DENIED = "42501";

const adminUrl = databaseUrl();
const testDbName = `sentinelx_test_${process.pid}_${Date.now()}`;
const testUrl = (() => {
  const url = new URL(adminUrl);
  url.pathname = `/${testDbName}`;
  return url.toString();
})();

let pool: pg.Pool;
let db: NodePgDatabase;

async function adminQuery(text: string): Promise<void> {
  const client = new pg.Client({ connectionString: adminUrl });
  await client.connect();
  try {
    await client.query(text);
  } finally {
    await client.end();
  }
}

/** PostgreSQL SQLSTATE of a failed query; drizzle may wrap the driver error in `cause`. */
async function pgCode(promise: Promise<unknown>): Promise<string | null> {
  try {
    await promise;
    return null;
  } catch (error: unknown) {
    const e = error as { code?: string; cause?: { code?: string } };
    return e.code ?? e.cause?.code ?? "unknown";
  }
}

/** First row of a query result; fails the test instead of yielding undefined. */
function first<T>(rows: T[]): T {
  const [row] = rows;
  if (row === undefined) throw new Error("expected at least one row");
  return row;
}

/** Runs one statement as `role` inside a rolled-back transaction; returns the SQLSTATE or null if allowed. */
async function asRole(role: string, text: string): Promise<string | null> {
  const client = await pool.connect();
  try {
    await client.query("BEGIN");
    await client.query(`SET LOCAL ROLE ${role}`);
    return await pgCode(client.query(text));
  } finally {
    await client.query("ROLLBACK");
    client.release();
  }
}

const newEvent = (externalEventId: string) => ({
  externalEventId,
  occurredAt: new Date("2026-01-01T10:00:00Z"),
  userId: "user_1",
  sourceIp: "192.0.2.10",
  eventType: "authentication",
  action: "login",
  resource: "portal",
  status: "failed",
});

beforeAll(async () => {
  await adminQuery(`CREATE DATABASE ${testDbName}`);
  await runMigrations(testUrl);
  pool = new pg.Pool({ connectionString: testUrl, max: 4 });
  db = drizzle(pool);
  await seedReferenceData(db);
});

afterAll(async () => {
  await pool?.end();
  await adminQuery(`DROP DATABASE IF EXISTS ${testDbName} WITH (FORCE)`);
});

describe("migrations", () => {
  it("migrate an empty database to exactly the documented tables", async () => {
    const result = await db.execute<{ table_name: string }>(
      sql`SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' ORDER BY table_name`,
    );
    expect(result.rows.map((r) => r.table_name)).toEqual(EXPECTED_TABLES);
  });

  it("record every journal entry and are a no-op when re-run", async () => {
    const journal = JSON.parse(readFileSync(`${MIGRATIONS_FOLDER}/meta/_journal.json`, "utf8")) as {
      entries: unknown[];
    };
    const count = async () =>
      Number((await db.execute<{ n: string }>(sql`SELECT count(*) AS n FROM drizzle.__drizzle_migrations`)).rows[0]?.n);
    expect(await count()).toBe(journal.entries.length);
    await runMigrations(testUrl);
    expect(await count()).toBe(journal.entries.length);
  });
});

describe("CRUD and constraints", () => {
  it("creates, reads, updates and deletes an event with a database-generated prefixed id", async () => {
    const { id } = first(await db.insert(securityEvents).values(newEvent("evt_crud")).returning());
    expect(id).toMatch(/^se_[0-9a-f]{16}$/);

    const [read] = await db.select().from(securityEvents).where(eq(securityEvents.id, id));
    expect(read?.sourceIp).toBe("192.0.2.10");
    expect(read?.metadataJson).toEqual({});

    await db.update(securityEvents).set({ status: "success" }).where(eq(securityEvents.id, id));
    const [updated] = await db.select().from(securityEvents).where(eq(securityEvents.id, id));
    expect(updated?.status).toBe("success");

    await db.delete(securityEvents).where(eq(securityEvents.id, id));
    expect(await db.select().from(securityEvents).where(eq(securityEvents.id, id))).toHaveLength(0);
  });

  it("enforces idempotency, foreign keys, score bounds and IP validity", async () => {
    await db.insert(securityEvents).values(newEvent("evt_dup"));
    expect(await pgCode(db.insert(securityEvents).values(newEvent("evt_dup")))).toBe("23505");
    expect(
      await pgCode(
        db.insert(detectionSignals).values({
          eventId: "se_missing",
          ruleName: "r",
          ruleScore: 10,
          severity: "LOW",
          reason: "x",
        }),
      ),
    ).toBe("23503");
    expect(
      await pgCode(
        db.insert(incidents).values({ title: "t", riskScore: 101, severity: "CRITICAL", startedAt: new Date() }),
      ),
    ).toBe("23514");
    expect(await pgCode(db.insert(securityEvents).values({ ...newEvent("evt_bad_ip"), sourceIp: "not-an-ip" }))).toBe(
      "22P02",
    );
  });

  it("links the detection-to-investigation chain", async () => {
    const { id: eventId } = first(await db.insert(securityEvents).values(newEvent("evt_chain")).returning());
    await db.insert(detectionSignals).values({
      eventId,
      ruleName: "repeated_failed_logins",
      ruleScore: 60,
      severity: "HIGH",
      reason: "5 failures in 2 minutes",
    });
    const alert = first(
      await db
        .insert(alerts)
        .values({ eventId, riskScore: 88, anomalyScore: 0.71, modelVersion: "test", severity: "CRITICAL", reasonsJson: [] })
        .returning(),
    );
    const { id: incidentId } = first(
      await db
        .insert(incidents)
        .values({ title: "Possible compromise", riskScore: 88, severity: "CRITICAL", startedAt: new Date() })
        .returning(),
    );
    await db.insert(incidentEvents).values({ incidentId, eventId });
    await db.insert(incidentAlerts).values({ incidentId, alertId: alert.id });
    const run = first(await db.insert(investigationRuns).values({ incidentId }).returning());
    const runId = run.id;
    expect(run.status).toBe("queued");
    expect(run.requiresReview).toBe(false);
    const ev = first(
      await db
        .insert(evidence)
        .values({ investigationRunId: runId, sourceType: "event", sourceId: eventId, claim: "c", dataJson: {} })
        .returning(),
    );
    expect(ev.id).toMatch(/^ev_[0-9a-f]{16}$/);
    await db.insert(investigationTrace).values({ investigationRunId: runId, stepIndex: 0, actionType: "load_incident" });
    expect(
      await pgCode(
        db.insert(investigationTrace).values({ investigationRunId: runId, stepIndex: 0, actionType: "duplicate" }),
      ),
    ).toBe("23505");
  });
});

describe("reference data seeds", () => {
  const fixtureLength = (name: string, key: string) =>
    (JSON.parse(readFileSync(new URL(`../../../../fixtures/${name}`, import.meta.url), "utf8")) as Record<string, unknown[]>)[
      key
    ]?.length;

  it("load every fixture row and are idempotent", async () => {
    const counts = async () => ({
      ips: (await db.select().from(ipReputation)).length,
      techniques: (await db.select().from(mitreTechniques)).length,
    });
    const expected = {
      ips: fixtureLength("ip_reputation.json", "entries"),
      techniques: fixtureLength("mitre_techniques.json", "techniques"),
    };
    expect(await counts()).toEqual(expected);
    await seedReferenceData(db);
    expect(await counts()).toEqual(expected);
  });

  it("remove rows that are no longer in the fixture", async () => {
    await db.insert(ipReputation).values({ ip: "10.99.99.99", reputation: "unknown", score: 1, source: "stale" });
    await seedReferenceData(db);
    expect(await db.select().from(ipReputation).where(eq(ipReputation.ip, "10.99.99.99"))).toHaveLength(0);
  });

  it("serve the values the agent tools will read", async () => {
    const [ip] = await db.select().from(ipReputation).where(eq(ipReputation.ip, "203.0.113.45"));
    expect(ip).toMatchObject({ reputation: "malicious", score: 90 });
    const [technique] = await db.select().from(mitreTechniques).where(eq(mitreTechniques.techniqueId, "T1110"));
    expect(technique).toMatchObject({ name: "Brute Force", tacticsJson: ["credential-access"] });
  });
});

describe("role permissions", () => {
  let runId: string;

  beforeAll(async () => {
    const incident = first(
      await db
        .insert(incidents)
        .values({ title: "role test", riskScore: 50, severity: "MEDIUM", startedAt: new Date() })
        .returning(),
    );
    runId = first(await db.insert(investigationRuns).values({ incidentId: incident.id }).returning()).id;
  });

  const insertEvent =
    "INSERT INTO security_events (external_event_id, occurred_at, user_id, source_ip, event_type, action, resource, status) " +
    "VALUES ('evt_role', now(), 'user_1', '192.0.2.10', 'authentication', 'login', 'portal', 'failed')";
  const insertEvidence = () =>
    "INSERT INTO evidence (investigation_run_id, source_type, source_id, claim, data_json) " +
    `VALUES ('${runId}', 'event', 'se_x', 'c', '{}')`;

  it.each([
    // Agent tools: SELECT-only, no analysts or investigation records.
    ["sentinelx_ai_tools", "SELECT 1 FROM security_events", null],
    ["sentinelx_ai_tools", "SELECT 1 FROM ip_reputation", null],
    ["sentinelx_ai_tools", "SELECT 1 FROM mitre_techniques", null],
    ["sentinelx_ai_tools", "SELECT 1 FROM analysts", DENIED],
    ["sentinelx_ai_tools", "SELECT 1 FROM evidence", DENIED],
    ["sentinelx_ai_tools", insertEvent, DENIED],
    ["sentinelx_ai_tools", "UPDATE incidents SET title = title", DENIED],
    ["sentinelx_ai_tools", "DELETE FROM security_events", DENIED],
    ["sentinelx_ai_tools", "CREATE TABLE tool_probe (id int)", DENIED],
    // AI writer: run status updates, append-only trace/evidence.
    ["sentinelx_ai_writer", "UPDATE investigation_runs SET status = 'running'", null],
    ["sentinelx_ai_writer", "UPDATE evidence SET claim = claim", DENIED],
    ["sentinelx_ai_writer", "DELETE FROM evidence", DENIED],
    ["sentinelx_ai_writer", "UPDATE investigation_trace SET action_type = action_type", DENIED],
    ["sentinelx_ai_writer", insertEvent, DENIED],
    ["sentinelx_ai_writer", "SELECT 1 FROM analysts", DENIED],
    // App (web + detection): pipeline writes, no deletes, no investigation writes.
    ["sentinelx_app", insertEvent, null],
    ["sentinelx_app", "SELECT 1 FROM analysts", null],
    ["sentinelx_app", "DELETE FROM security_events", DENIED],
    ["sentinelx_app", "TRUNCATE security_events", DENIED],
    ["sentinelx_app", "INSERT INTO investigation_runs (incident_id) VALUES ('inc_x')", DENIED],
    ["sentinelx_app", "INSERT INTO ip_reputation (ip, reputation, score, source) VALUES ('10.1.1.1', 'unknown', 1, 'x')", DENIED],
    ["sentinelx_app", "CREATE TABLE app_probe (id int)", DENIED],
    // Sessions (D-034/D-035): web app reads, creates and revokes; nobody deletes; AI roles have no access.
    ["sentinelx_app", "SELECT 1 FROM analyst_sessions", null],
    ["sentinelx_app", "UPDATE analyst_sessions SET revoked_at = now()", null],
    ["sentinelx_app", "DELETE FROM analyst_sessions", DENIED],
    ["sentinelx_ai_tools", "SELECT 1 FROM analyst_sessions", DENIED],
    ["sentinelx_ai_writer", "SELECT 1 FROM analyst_sessions", DENIED],
  ])("%s: %s -> %s", async (role, statement, expected) => {
    expect(await asRole(role, statement)).toBe(expected);
  });

  it("sentinelx_ai_writer can append evidence", async () => {
    expect(await asRole("sentinelx_ai_writer", insertEvidence())).toBeNull();
  });

  it("sentinelx_ai_writer cannot log in until Phase 08 enables it (app and tools roles may, via db:roles)", async () => {
    const result = await db.execute<{ rolcanlogin: boolean }>(
      sql`SELECT rolcanlogin FROM pg_roles WHERE rolname = 'sentinelx_ai_writer'`,
    );
    expect(result.rows).toEqual([{ rolcanlogin: false }]);
  });
});

describe("analyst sessions (D-034)", () => {
  const password = "a-long-test-password";
  let analystId: string;

  beforeAll(async () => {
    analystId = (await createAnalyst(db, { email: " Session.Test@Example.Local ", name: "Session Test", password })).id;
  });

  it("stores normalized emails and rejects duplicates, weak passwords and malformed emails", async () => {
    await expect(createAnalyst(db, { email: "session.test@example.local", name: "Dup", password })).rejects.toThrow(
      /already exists/,
    );
    await expect(createAnalyst(db, { email: "weak@example.local", name: "Weak", password: "short" })).rejects.toThrow(
      /at least/,
    );
    await expect(createAnalyst(db, { email: "not-an-email", name: "Bad", password })).rejects.toThrow(/invalid email/);
  });

  it("authenticates by normalized email and rejects wrong passwords and unknown accounts", async () => {
    expect(await authenticate(db, "SESSION.TEST@example.local", password)).toEqual({ id: analystId, name: "Session Test" });
    expect(await authenticate(db, "session.test@example.local", "wrong-password-123")).toBeNull();
    expect(await authenticate(db, "nobody@example.local", password)).toBeNull();
  });

  it("resolves sessions until expiry or revocation and stores only the token hash", async () => {
    const now = new Date("2026-03-01T12:00:00Z");
    const { token, expiresAt } = await createSession(db, analystId, now);
    expect(expiresAt.getTime() - now.getTime()).toBe(SESSION_TTL_MS);
    expect(await findActiveSession(db, token, now)).toMatchObject({ analystId, name: "Session Test" });

    const stored = await db.execute<{ token_hash: string }>(
      sql`SELECT token_hash FROM analyst_sessions WHERE analyst_id = ${analystId}`,
    );
    expect(stored.rows.map((r) => r.token_hash)).not.toContain(token);

    expect(await findActiveSession(db, token, new Date(expiresAt.getTime() + 1))).toBeNull();
    await revokeSession(db, token, now);
    expect(await findActiveSession(db, token, now)).toBeNull();
    expect(await findActiveSession(db, "not-a-token", now)).toBeNull();
  });
});
