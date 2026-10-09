// Phase 02 exit: the UI runs; auth boundary; empty, not-found, populated and degraded states; API 401/404/503.
// Phase 08: investigation endpoints (AI service unreachable here; the live graph is tested in services/ai).
import { expect, test, type Page } from "@playwright/test";
import pg from "pg";
import { DEGRADED_URL, E2E_ANALYST, HEALTHY_URL, e2eOwnerUrl } from "./support.ts";

const UNKNOWN_INCIDENT = "inc_0000000000000000";

async function signIn(page: Page, password: string = E2E_ANALYST.password): Promise<void> {
  await page.goto("/login");
  await page.getByLabel("Email").fill(E2E_ANALYST.email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
}

async function sessionCookie(page: Page) {
  return (await page.context().cookies()).find((cookie) => cookie.name === "sx_session");
}

async function insertReturningId(client: pg.Client, text: string, values: unknown[] = []): Promise<string> {
  const result = await client.query<{ id: string }>(text, values);
  const id = result.rows[0]?.id;
  if (!id) throw new Error(`insert returned no id: ${text}`);
  return id;
}

test.describe.configure({ mode: "serial" });

test.describe("healthy server", () => {
  test("redirects unauthenticated visitors to sign-in", async ({ page }) => {
    for (const path of ["/", "/incidents", "/events", `/incidents/${UNKNOWN_INCIDENT}`]) {
      await page.goto(path);
      await expect(page).toHaveURL(/\/login$/);
    }
    await expect(page.getByRole("heading", { name: "SentinelX" })).toBeVisible();
  });

  test("API rejects requests without a session", async ({ request }) => {
    const calls: [string, string][] = [
      ["GET", "/api/incidents"],
      ["GET", `/api/incidents/${UNKNOWN_INCIDENT}`],
      ["POST", "/api/events"],
      ["POST", `/api/incidents/${UNKNOWN_INCIDENT}/investigate`],
      ["GET", "/api/investigations/run_0000000000000000"],
      ["PATCH", `/api/incidents/${UNKNOWN_INCIDENT}`],
    ];
    for (const [method, path] of calls) {
      const response = await request.fetch(path, { method });
      expect(response.status(), `${method} ${path}`).toBe(401);
      expect(await response.json()).toMatchObject({ error: { code: "unauthorized" } });
    }
  });

  test("rejects wrong credentials, keeps the email and allows a retry on the same page", async ({ page }) => {
    await signIn(page, "wrong-password-123");
    await expect(page.getByText("Invalid email or password.")).toBeVisible();
    await expect(page).toHaveURL(/\/login$/);
    expect(await sessionCookie(page)).toBeUndefined();
    await expect(page.getByLabel("Email")).toHaveValue(E2E_ANALYST.email);
    await expect(page.getByLabel("Password")).toHaveValue("");

    await page.getByLabel("Password").fill(E2E_ANALYST.password);
    await page.getByRole("button", { name: "Sign in" }).click();
    await expect(page).toHaveURL(`${HEALTHY_URL}/`);
  });

  test("signs in and shows empty states with real zero counts", async ({ page }) => {
    await signIn(page);
    await expect(page).toHaveURL(`${HEALTHY_URL}/`);
    await expect(page.getByTestId("analyst-name")).toHaveText(E2E_ANALYST.name);
    await expect(page.getByTestId("open-incidents")).toHaveText("0");
    await expect(page.getByTestId("events-24h")).toHaveText("0");
    await expect(page.getByTestId("alerts-24h")).toHaveText("0");
    await expect(page.getByText("No incidents")).toBeVisible();
    expect(await sessionCookie(page)).toMatchObject({ httpOnly: true, sameSite: "Lax", secure: true, path: "/" });

    await page.getByRole("link", { name: "Incidents", exact: true }).click();
    await expect(page.getByRole("heading", { name: "Incidents" })).toBeVisible();
    await expect(page.getByText("No incidents")).toBeVisible();

    await page.getByRole("link", { name: "Events", exact: true }).click();
    await expect(page.getByRole("heading", { name: "Events" })).toBeVisible();
    await expect(page.getByText("No security events")).toBeVisible();

    for (const id of [UNKNOWN_INCIDENT, "not-an-incident-id"]) {
      await page.goto(`/incidents/${id}`);
      await expect(page.getByText("Incident not found")).toBeVisible();
    }
  });

  test("API serves real data and 404 for unknown investigation targets", async ({ page }) => {
    await signIn(page);
    await expect(page).toHaveURL(`${HEALTHY_URL}/`);
    const list = await page.request.get("/api/incidents");
    expect(list.status()).toBe(200);
    expect(await list.json()).toEqual({ incidents: [] });
    expect((await page.request.get("/api/incidents/not-an-id")).status()).toBe(404);

    const unknown: [string, string][] = [
      ["POST", `/api/incidents/${UNKNOWN_INCIDENT}/investigate`],
      ["POST", "/api/incidents/not-an-id/investigate"],
      ["GET", "/api/investigations/run_0000000000000000"],
      ["GET", "/api/investigations/not-a-run"],
    ];
    for (const [method, path] of unknown) {
      const response = await page.request.fetch(path, { method });
      expect(response.status(), `${method} ${path}`).toBe(404);
      expect(await response.json()).toMatchObject({ error: { code: "not_found" } });
    }
  });

  test("shows a persisted incident with its linked events", async ({ page }) => {
    const client = new pg.Client({ connectionString: e2eOwnerUrl() });
    await client.connect();
    let incidentId: string;
    try {
      const eventId = await insertReturningId(
        client,
        `INSERT INTO security_events (external_event_id, occurred_at, user_id, source_ip, event_type, action, resource, status)
         VALUES ('evt_e2e_1', '2026-01-01T10:00:00Z', 'user_1', '203.0.113.45', 'authentication', 'login', 'portal', 'success')
         RETURNING id`,
      );
      incidentId = await insertReturningId(
        client,
        `INSERT INTO incidents (title, risk_score, severity, primary_user_id, primary_ip, started_at)
         VALUES ('E2E possible compromise', 91, 'CRITICAL', 'user_1', '203.0.113.45', '2026-01-01T10:00:00Z')
         RETURNING id`,
      );
      await client.query("INSERT INTO incident_events (incident_id, event_id) VALUES ($1, $2)", [incidentId, eventId]);
    } finally {
      await client.end();
    }

    await signIn(page);
    await expect(page).toHaveURL(`${HEALTHY_URL}/`);
    await expect(page.getByTestId("open-incidents")).toHaveText("1");

    await page.goto("/incidents");
    const row = page.getByRole("row", { name: /E2E possible compromise/ });
    await expect(row).toContainText("CRITICAL");
    await expect(row).toContainText("91");
    await expect(row).toContainText("203.0.113.45");
    await row.getByRole("link", { name: "E2E possible compromise" }).click();

    await expect(page).toHaveURL(`${HEALTHY_URL}/incidents/${incidentId}`);
    await expect(page.getByTestId("risk-score")).toHaveText("91");
    await expect(page.getByRole("row", { name: /evt_e2e_1/ })).toContainText("2026-01-01 10:00:00Z");
    const detail = await page.request.get(`/api/incidents/${incidentId}`);
    expect(await detail.json()).toMatchObject({ incident: { id: incidentId, riskScore: 91, events: [{ externalEventId: "evt_e2e_1" }] } });
  });

  test("incident lifecycle via the page buttons and the API (D-054)", async ({ page }) => {
    await signIn(page);
    await expect(page).toHaveURL(`${HEALTHY_URL}/`);
    const listed = (await (await page.request.get("/api/incidents")).json()) as { incidents: { id: string }[] };
    const id = listed.incidents[0]?.id;
    if (!id) throw new Error("expected the incident created by the previous test");

    await page.goto(`/incidents/${id}`);
    const lifecycle = page.getByRole("form", { name: "Incident status" });
    await expect(lifecycle.getByRole("button")).toHaveText(["Start investigating", "Resolve"]);
    await lifecycle.getByRole("button", { name: "Start investigating" }).click();
    await expect(page.getByText("investigating", { exact: true })).toBeVisible();
    await expect(lifecycle.getByRole("button")).toHaveText(["Reopen", "Resolve"]);
    await lifecycle.getByRole("button", { name: "Resolve" }).click();
    await expect(lifecycle.getByRole("button")).toHaveText(["Reopen"]);

    const patch = (status: unknown, target = id) =>
      page.request.patch(`/api/incidents/${target}`, { data: JSON.stringify({ status }), headers: { "content-type": "application/json" } });
    const invalid = await patch("investigating"); // resolved -> investigating is not allowed
    expect(invalid.status()).toBe(409);
    expect(await invalid.json()).toMatchObject({ error: { code: "invalid_transition", current: "resolved" } });
    expect((await patch("bogus")).status()).toBe(400);
    expect((await patch("open", "inc_0000000000000000")).status()).toBe(404);
    const reopened = await patch("open");
    expect(reopened.status()).toBe(200);
    expect(await reopened.json()).toEqual({ incident: { id, status: "open" } });
    const extra = await page.request.patch(`/api/incidents/${id}`, {
      data: JSON.stringify({ status: "resolved", title: "renamed" }),
      headers: { "content-type": "application/json" },
    });
    expect(extra.status()).toBe(400); // only "status" may be changed
  });

  test("investigation: unavailable AI service, then a persisted run with trace and evidence (D-015)", async ({ page }) => {
    await signIn(page);
    await expect(page).toHaveURL(`${HEALTHY_URL}/`);
    const listed = (await (await page.request.get("/api/incidents")).json()) as { incidents: { id: string }[] };
    const id = listed.incidents[0]?.id;
    if (!id) throw new Error("expected the incident created earlier");

    const refused = await page.request.post(`/api/incidents/${id}/investigate`);
    expect(refused.status()).toBe(503);
    expect(await refused.json()).toMatchObject({ error: { code: "unavailable" } });
    await page.goto(`/incidents/${id}`);
    await expect(page.getByText("No investigation yet.")).toBeVisible();
    await page.getByRole("form", { name: "Investigation" }).getByRole("button", { name: "Investigate" }).click();
    await expect(page.getByRole("status")).toHaveText("The AI service is unavailable. Try again later.");

    // A run as the AI service persists it (writer role), read back through the web role.
    const client = new pg.Client({ connectionString: e2eOwnerUrl() });
    await client.connect();
    let runId: string;
    let evidenceId: string;
    try {
      runId = await insertReturningId(
        client,
        `INSERT INTO investigation_runs (incident_id, status, verdict_json, raw_output_json, model_name, prompt_version,
                                         started_at, completed_at)
         VALUES ($1, 'completed', $2, '{"attempts": []}', 'e2e-model', 'investigation-v1', now(), now()) RETURNING id`,
        [id, { verdict: "Possible Account Compromise", confidence: 0.7, severity: "HIGH" }],
      );
      evidenceId = await insertReturningId(
        client,
        `INSERT INTO evidence (investigation_run_id, source_type, source_id, claim, data_json)
         VALUES ($1, 'ip_reputation', '203.0.113.45', 'IP 203.0.113.45 local reputation malicious', '{}') RETURNING id`,
        [runId],
      );
      await client.query(
        `INSERT INTO investigation_trace (investigation_run_id, step_index, action_type, action_origin, tool_name, evidence_ids_json)
         VALUES ($1, 0, 'load_incident', NULL, NULL, '[]'), ($1, 1, 'tool_call', 'fallback', 'get_ip_reputation', $2)`,
        [runId, JSON.stringify([evidenceId])],
      );
    } finally {
      await client.end();
    }

    const response = await page.request.get(`/api/investigations/${runId}`);
    expect(response.status()).toBe(200);
    const body = (await response.json()) as { investigation: Record<string, unknown> };
    expect(body).toMatchObject({
      investigation: {
        id: runId,
        incidentId: id,
        status: "completed",
        requiresReview: false,
        verdict: { verdict: "Possible Account Compromise" },
        trace: [
          { stepIndex: 0, actionType: "load_incident", actionOrigin: null },
          { stepIndex: 1, actionType: "tool_call", actionOrigin: "fallback", toolName: "get_ip_reputation", evidenceIds: [evidenceId] },
        ],
        evidence: [{ id: evidenceId, sourceType: "ip_reputation", sourceId: "203.0.113.45" }],
      },
    });
    expect(body.investigation).not.toHaveProperty("rawOutput"); // audit copy stays server-side (D-019)

    await page.goto(`/incidents/${id}`);
    const latest = page.getByTestId("latest-investigation");
    await expect(latest).toContainText(runId);
    await expect(latest).toContainText("completed");
  });

  test("sign-out revokes the session server-side", async ({ page, browser }) => {
    await signIn(page);
    await expect(page).toHaveURL(`${HEALTHY_URL}/`);
    const token = (await sessionCookie(page))?.value;
    if (!token) throw new Error("no session cookie after sign-in");

    await page.getByRole("button", { name: "Sign out" }).click();
    await expect(page).toHaveURL(/\/login$/);
    expect(await sessionCookie(page)).toBeUndefined();

    // Replaying the old token must fail: the session is revoked in PostgreSQL, not only removed from the browser.
    const replay = await browser.newContext({ baseURL: HEALTHY_URL });
    await replay.addCookies([{ name: "sx_session", value: token, url: HEALTHY_URL }]);
    const replayPage = await replay.newPage();
    await replayPage.goto("/incidents");
    await expect(replayPage).toHaveURL(/\/login$/);
    expect((await replay.request.get("/api/incidents")).status()).toBe(401);
    await replay.close();
  });
});

test.describe("degraded server: database unreachable", () => {
  test.use({ baseURL: DEGRADED_URL });

  test("sign-in reports the outage instead of failing", async ({ page }) => {
    await signIn(page);
    await expect(page.getByText("Sign-in is temporarily unavailable. Try again shortly.")).toBeVisible();
    await expect(page).toHaveURL(/\/login$/);
  });

  test("console and API report unavailability", async ({ page, context }) => {
    await context.addCookies([{ name: "sx_session", value: "A".repeat(43), url: DEGRADED_URL }]);
    await page.goto("/incidents");
    await expect(page.getByRole("heading", { name: "Service unavailable" })).toBeVisible();
    const response = await page.request.get("/api/incidents");
    expect(response.status()).toBe(503);
    expect(await response.json()).toMatchObject({ error: { code: "unavailable" } });
  });
});
