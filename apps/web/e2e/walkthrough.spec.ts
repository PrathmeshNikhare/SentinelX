// Phase 11 exit: a complete attack scenario is understandable from the incident page alone (docs/09 order).
// Runs after shell.spec.ts (files run alphabetically, one worker). Data is written as the owner exactly as the
// detection worker and the AI service persist it; the live pipeline is covered in services/detection and services/ai.
import { readFileSync } from "node:fs";
import { expect, test, type Page } from "@playwright/test";
import pg from "pg";
import { E2E_ANALYST, HEALTHY_URL, e2eOwnerUrl } from "./support.ts";

const SECTION_ORDER = [
  "Summary",
  "Timeline",
  "Detection signals",
  "Investigation trace",
  "Evidence",
  "MITRE ATT&CK",
  "Verdict",
  "Recommendations",
];
// Rule hits per scenario-A event index, as the Phase 04 rules produce them.
const SIGNALS: Record<number, [string, number][]> = {
  4: [["brute_force_attempts", 60]],
  5: [["login_after_failures", 75], ["risky_ip_login", 90]],
  6: [["suspicious_powershell", 85], ["post_compromise_chain", 85]],
  7: [["sensitive_file_access", 50], ["post_compromise_chain", 85]],
  8: [["sensitive_file_access", 50], ["post_compromise_chain", 85]],
};
const ALERT_RISK: Record<number, number> = { 5: 90, 6: 88 };

interface ScenarioEvent {
  offset_seconds: number;
  user_id: string;
  source_ip: string;
  event_type: string;
  action: string;
  resource: string;
  status: string;
  metadata?: Record<string, unknown>;
}

async function one(client: pg.Client, text: string, values: unknown[]): Promise<string> {
  const id = (await client.query<{ id: string }>(text, values)).rows[0]?.id;
  if (!id) throw new Error(`insert returned no id: ${text}`);
  return id;
}

async function seedScenario(client: pg.Client, tag: string) {
  const scenario = JSON.parse(readFileSync(new URL("../../../fixtures/scenarios/scenario-a.json", import.meta.url), "utf8")) as {
    events: ScenarioEvent[];
  };
  const base = Date.UTC(2026, 9, 8, 14, 0, 0);
  const incidentId = await one(
    client,
    `INSERT INTO incidents (title, risk_score, severity, primary_user_id, primary_ip, started_at)
     VALUES ('Possible account compromise: alice', 90, 'CRITICAL', 'alice', '203.0.113.45', $1) RETURNING id`,
    [new Date(base)],
  );
  const eventIds: string[] = [];
  for (const [i, e] of scenario.events.entries()) {
    const eventId = await one(
      client,
      `INSERT INTO security_events (external_event_id, occurred_at, user_id, source_ip, event_type, action, resource, status, metadata_json)
       VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9) RETURNING id`,
      [`demo-a-${tag}-${i + 1}`, new Date(base + e.offset_seconds * 1000), e.user_id, e.source_ip, e.event_type, e.action, e.resource, e.status, e.metadata ?? {}],
    );
    eventIds.push(eventId);
    await client.query("INSERT INTO incident_events (incident_id, event_id) VALUES ($1, $2)", [incidentId, eventId]);
    for (const [rule, score] of SIGNALS[i] ?? []) {
      await client.query(
        `INSERT INTO detection_signals (event_id, rule_name, rule_score, severity, reason) VALUES ($1, $2, $3, $4, $5)`,
        [eventId, rule, score, score >= 85 ? "CRITICAL" : score >= 70 ? "HIGH" : "MEDIUM", `${rule} fired`],
      );
    }
    const risk = ALERT_RISK[i];
    if (risk) {
      const reasons = {
        signals: (SIGNALS[i] ?? []).map(([rule, score]) => ({ rule, score, reason: `${rule} fired` })),
        components: { rule: 90, anomaly: 0.81, reputation: 90, context: 75 },
        formula: "0.45R + 0.25A + 0.2P + 0.1C",
      };
      const alertId = await one(
        client,
        `INSERT INTO alerts (event_id, risk_score, anomaly_score, model_version, severity, reasons_json)
         VALUES ($1, $2, 0.81, 'iforest-v1-e2e', 'CRITICAL', $3) RETURNING id`,
        [eventId, risk, reasons],
      );
      await client.query("INSERT INTO incident_alerts (incident_id, alert_id) VALUES ($1, $2)", [incidentId, alertId]);
    }
  }
  return { incidentId, eventIds };
}

async function seedRun(client: pg.Client, incidentId: string, eventIds: string[]) {
  const runId = await one(
    client,
    `INSERT INTO investigation_runs (incident_id, status, model_name, prompt_version, started_at, created_at)
     VALUES ($1, 'running', 'llama3.2:3b', 'investigation-v2', now(), now() - interval '2 minutes') RETURNING id`,
    [incidentId],
  );
  const evidence = async (sourceType: string, sourceId: string, claim: string, data: unknown) =>
    one(
      client,
      `INSERT INTO evidence (investigation_run_id, source_type, source_id, claim, data_json) VALUES ($1, $2, $3, $4, $5) RETURNING id`,
      [runId, sourceType, sourceId, claim, data],
    );
  const evFailed = await evidence("event", eventIds[4] ?? "", "2026-10-08T14:01:20Z alice authentication/login failed from 203.0.113.45", {});
  const evSuccess = await evidence("event", eventIds[5] ?? "", "2026-10-08T14:01:40Z alice authentication/login success from 203.0.113.45", {});
  const evIp = await evidence("ip_reputation", "203.0.113.45", "IP 203.0.113.45 local reputation malicious (score 90; brute-force-source, botnet)", {
    ip: "203.0.113.45",
    known: true,
  });
  const evMitre = await evidence("mitre", "T1110", "MITRE ATT&CK T1110 Brute Force (credential-access)", { technique_id: "T1110", found: true });
  const evKnowledge = await evidence("knowledge", "kd_00000000000000aa", "T1078 Valid Accounts (mitre-attack T1078)", {
    document_id: "kd_00000000000000aa",
    source: "mitre-attack",
    external_id: "T1078",
  });
  await client.query(
    `INSERT INTO investigation_trace (investigation_run_id, step_index, action_type, action_origin, tool_name, input_json, result_json, evidence_ids_json)
     VALUES ($1, 0, 'load_incident', NULL, NULL, NULL, '{"events": 9, "alerts": 2}', $2),
            ($1, 1, 'choose_action', 'llm', 'get_ip_reputation', NULL, '{"reason": "accepted"}', '[]'),
            ($1, 2, 'tool_call', 'llm', 'get_ip_reputation', '{"ip": "203.0.113.45"}', '{"ok": true}', $3),
            ($1, 3, 'choose_action', 'fallback', 'get_mitre_technique', NULL, '{"reason": "duplicate of an earlier action"}', '[]'),
            ($1, 4, 'tool_call', 'fallback', 'get_mitre_technique', '{"technique_id": "T1110"}', '{"ok": true}', $4),
            ($1, 5, 'build_verdict', 'llm', NULL, NULL, '{"attempts": 1, "valid": true}', '[]'),
            ($1, 6, 'validate_verdict', NULL, NULL, NULL, '{"accepted": true, "requires_review": false}', $5)`,
    [runId, JSON.stringify([evFailed, evSuccess]), JSON.stringify([evIp]), JSON.stringify([evMitre]), JSON.stringify([evFailed, evSuccess, evIp])],
  );
  const verdict = {
    verdict: "Possible account compromise",
    confidence: 0.83,
    severity: "HIGH",
    summary: "Failed logins from a malicious IP were followed by a successful login from the same address.",
    evidence_ids: [evFailed, evSuccess, evIp],
    mitre_techniques: ["T1110", "T1078"],
    recommendations: ["Reset alice's password", "Revoke active sessions"],
  };
  const note = { attempt: 0, code: "severity_disagreement", detail: "AI-assessed HIGH vs deterministic CRITICAL (1 level(s))", effect: "note" };
  return { runId, verdict, note, evIp, evKnowledge };
}

async function signIn(page: Page): Promise<void> {
  await page.goto("/login");
  await page.getByLabel("Email").fill(E2E_ANALYST.email);
  await page.getByLabel("Password").fill(E2E_ANALYST.password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(`${HEALTHY_URL}/`);
}

test.describe.configure({ mode: "serial" });

test("an analyst can follow scenario A from detection to a grounded verdict on one page", async ({ page }) => {
  const client = new pg.Client({ connectionString: e2eOwnerUrl() });
  await client.connect();
  try {
    const { incidentId, eventIds } = await seedScenario(client, "walkthrough");
    const run = await seedRun(client, incidentId, eventIds);

    await signIn(page);
    await page.goto(`/incidents/${incidentId}`);
    // A running investigation: status shown, Investigate disabled, page refreshes by itself (D-015 polling).
    await expect(page.getByTestId("latest-investigation")).toContainText("running…");
    await expect(page.getByRole("form", { name: "Investigation" }).getByRole("button", { name: "Investigate" })).toBeDisabled();
    await client.query(
      `UPDATE investigation_runs SET status = 'completed', completed_at = now(), verdict_json = $2, raw_output_json = $3,
       validation_errors_json = $4 WHERE id = $1`,
      [run.runId, run.verdict, { attempts: [{ valid: true, output: run.verdict }] }, JSON.stringify([run.note])],
    );
    await expect(page.getByTestId("latest-investigation")).toContainText("completed", { timeout: 15_000 });

    // docs/09 order.
    const headings = await page.getByRole("heading", { level: 2 }).allTextContents();
    expect(headings).toEqual(SECTION_ORDER);
    await expect(page.getByText("demo scenario data")).toBeVisible();

    const summary = page.getByTestId("incident-summary");
    await expect(summary).toContainText("9");
    await expect(summary).toContainText("203.0.113.45");
    await expect(summary).toContainText("brute_force_attempts");

    const timeline = page.getByTestId("timeline");
    await expect(timeline.getByRole("row")).toHaveCount(10); // header + 9 events
    await expect(timeline.getByRole("row", { name: /demo-a-walkthrough-6/ })).toContainText("alert · risk 90");
    await expect(timeline.getByRole("row", { name: /demo-a-walkthrough-7/ })).toContainText("suspicious_powershell");

    const signals = page.getByTestId("detection-signals");
    await expect(signals.getByRole("row")).toHaveCount(3);
    await expect(signals).toContainText("login_after_failures (75)");
    await expect(signals).toContainText("R 90 · A 0.81 · P 90 · C 75");

    const trace = page.getByTestId("trace");
    await expect(trace.getByRole("row")).toHaveCount(8);
    await expect(trace.getByRole("row", { name: /duplicate of an earlier action/ })).toContainText("fallback");

    const evidence = page.getByTestId("evidence");
    await expect(evidence.getByRole("listitem")).toHaveCount(5);
    await expect(evidence.locator(`[id="${run.evIp}"]`)).toContainText("cited in verdict");

    const mitre = page.getByTestId("mitre");
    await expect(mitre).toContainText("T1110");
    await expect(mitre).toContainText("Brute Force");
    await expect(mitre.getByRole("listitem").filter({ hasText: "T1078" })).toContainText(run.evKnowledge);

    const verdict = page.getByTestId("verdict");
    await expect(verdict).toContainText("Possible account compromise");
    await expect(verdict).toContainText("AI-assessed severity");
    await expect(verdict).toContainText("Confidence (model-reported, uncalibrated)");
    await expect(verdict).toContainText("risk 90/100");
    await expect(page.getByTestId("review-banner")).toHaveCount(0); // a one-level difference is only a note

    await expect(page.getByTestId("recommendations").getByRole("listitem")).toHaveText(["Reset alice's password", "Revoke active sessions"]);

    await page.screenshot({ path: test.info().outputPath("incident-walkthrough.png"), fullPage: true }); // for review
    await verdict.getByRole("link", { name: run.evIp }).click();
    await expect(page).toHaveURL(new RegExp(`#${run.evIp}$`));
  } finally {
    await client.end();
  }
});

test("a rejected verdict shows the review banner with readable findings and no verdict", async ({ page }) => {
  const client = new pg.Client({ connectionString: e2eOwnerUrl() });
  await client.connect();
  try {
    const { incidentId } = await seedScenario(client, "review");
    const findings = [
      { attempt: 0, code: "unknown_evidence_id", detail: "evidence_ids[0] ev_ffffffffffffffff", effect: "reject" },
      { attempt: 1, code: "unknown_mitre_technique", detail: "mitre_techniques[0] T1003", effect: "reject" },
    ];
    await client.query(
      `INSERT INTO investigation_runs (incident_id, status, requires_review, raw_output_json, validation_errors_json, model_name,
                                       prompt_version, started_at, completed_at)
       VALUES ($1, 'completed', true, '{"attempts": []}', $2, 'llama3.2:3b', 'investigation-v2', now(), now())`,
      [incidentId, JSON.stringify(findings)],
    );

    await signIn(page);
    await page.goto(`/incidents/${incidentId}`);
    const banner = page.getByTestId("review-banner");
    await expect(banner).toContainText("Requires analyst review: no verdict was accepted");
    await expect(banner).toContainText("Cited evidence that is not part of this investigation");
    await expect(banner).toContainText("MITRE technique outside the curated ATT&CK set");
    await expect(banner).toContainText("attempt 2");
    await expect(page.getByText("No accepted verdict")).toBeVisible();
    await expect(page.getByTestId("verdict")).toHaveCount(0);
    await expect(page.getByText("No recommendations")).toBeVisible();
    await page.screenshot({ path: test.info().outputPath("incident-review.png"), fullPage: true });
  } finally {
    await client.end();
  }
});
