// Phase 03 exit: events travel through POST /api/events into Kafka; validation, auth and failure paths.
import { expect, test, type APIRequestContext, type Page } from "@playwright/test";
import { consumeEventIds, parseBrokers } from "../src/ingest/kafka.ts";
import { defaultBase, expandScenario, loadScenario, sendEvents } from "../src/demo/scenarios.ts";
import { DEGRADED_URL, E2E_ANALYST, E2E_EVENTS_TOPIC, E2E_INGEST_TOKEN, HEALTHY_URL, kafkaBrokers } from "./support.ts";

const brokers = parseBrokers(kafkaBrokers());
const bearer = { authorization: `Bearer ${E2E_INGEST_TOKEN}` };
const uid = () => `e2e-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;

const event = (overrides: Record<string, unknown> = {}) => ({
  event_id: uid(),
  timestamp: new Date().toISOString(),
  user_id: "E2E.User",
  source_ip: "192.0.2.10",
  event_type: "authentication",
  action: "Login",
  resource: "vpn-portal",
  status: "failed",
  metadata: { auth_method: "password" },
  ...overrides,
});

async function post(request: APIRequestContext, data: unknown, headers: Record<string, string> = bearer) {
  return request.post("/api/events", { data: JSON.stringify(data), headers: { "content-type": "application/json", ...headers } });
}

async function signIn(page: Page): Promise<void> {
  await page.goto("/login");
  await page.getByLabel("Email").fill(E2E_ANALYST.email);
  await page.getByLabel("Password").fill(E2E_ANALYST.password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(`${HEALTHY_URL}/`);
}

test.describe.configure({ mode: "serial" });

test.describe("healthy server", () => {
  test("a token-authenticated event is normalized and lands in Kafka", async ({ request }) => {
    const body = event({ source_ip: "2001:DB8::0001" });
    const response = await post(request, body);
    expect(response.status()).toBe(202);
    expect(await response.json()).toEqual({ event_id: body.event_id, status: "accepted" });

    const found = await consumeEventIds(brokers, E2E_EVENTS_TOPIC, [body.event_id]);
    const message = found.get(body.event_id);
    expect(message?.key).toBe("e2e.user");
    expect(message?.headers).toMatchObject({ "schema-version": "v1" });
    expect(message?.value).toMatchObject({
      schema_version: "v1",
      event_id: body.event_id,
      user_id: "e2e.user",
      action: "login",
      source_ip: "2001:db8::1",
      metadata: { auth_method: "password" },
    });
  });

  test("an analyst session can also ingest", async ({ page }) => {
    await signIn(page);
    const body = event();
    const response = await post(page.request, body, {});
    expect(response.status()).toBe(202);
    expect((await consumeEventIds(brokers, E2E_EVENTS_TOPIC, [body.event_id])).has(body.event_id)).toBe(true);
  });

  test("rejects missing, wrong and malformed credentials", async ({ request }) => {
    expect((await post(request, event(), {})).status()).toBe(401);
    expect((await post(request, event(), { authorization: `Bearer ${E2E_INGEST_TOKEN}x` })).status()).toBe(401);
    expect((await post(request, event(), { authorization: `Basic ${E2E_INGEST_TOKEN}` })).status()).toBe(401);
  });

  test("validates the boundary: media type, size, JSON, contract, clock skew, __proto__", async ({ request }) => {
    const wrongType = await request.post("/api/events", { data: JSON.stringify(event()), headers: { ...bearer, "content-type": "text/plain" } });
    expect(wrongType.status()).toBe(415);

    const huge = await post(request, event({ metadata: { blob: "x".repeat(20_000) } }));
    expect(huge.status()).toBe(413);

    // A Buffer is sent verbatim; Playwright would JSON-encode a non-JSON string when Content-Type is JSON.
    const badJson = await request.post("/api/events", { data: Buffer.from("{not json"), headers: { ...bearer, "content-type": "application/json" } });
    expect(badJson.status()).toBe(400);
    expect(await badJson.json()).toMatchObject({ error: { code: "invalid_json" } });

    const invalid = await post(request, event({ source_ip: "999.1.1.1", event_type: "shell", extra: true }));
    expect(invalid.status()).toBe(400);
    const issues = ((await invalid.json()) as { error: { issues: { path: string }[] } }).error.issues.map((i) => i.path);
    expect(issues).toEqual(expect.arrayContaining(["source_ip", "event_type", "(root)"]));

    const future = await post(request, event({ timestamp: new Date(Date.now() + 10 * 60_000).toISOString() }));
    expect(future.status()).toBe(400);
    expect(await future.json()).toMatchObject({ error: { issues: [{ path: "timestamp" }] } });

    const proto = await request.post("/api/events", {
      data: JSON.stringify(event()).replace('"metadata":{', '"metadata":{"__proto__":{"admin":true},'),
      headers: { ...bearer, "content-type": "application/json" },
    });
    expect(proto.status()).toBe(400);
    expect(await proto.json()).toMatchObject({ error: { issues: [{ path: "(body)" }] } });
  });

  test("the demo generator sends scenario A and every event reaches Kafka", async () => {
    const scenario = loadScenario("A");
    const events = expandScenario(scenario, defaultBase(scenario, new Date()));
    const results = await sendEvents(HEALTHY_URL, E2E_INGEST_TOKEN, events);
    expect(results.map((r) => r.status)).toEqual(events.map(() => 202));

    const ids = events.map((e) => e.event_id);
    const found = await consumeEventIds(brokers, E2E_EVENTS_TOPIC, ids);
    expect([...found.keys()].sort()).toEqual([...ids].sort());
    expect(new Set([...found.values()].map((m) => m.key))).toEqual(new Set(["alice"]));
  });
});

test.describe("degraded server: database down, Kafka up", () => {
  test.use({ baseURL: DEGRADED_URL });

  test("token ingestion still works because it never touches PostgreSQL (D-014, D-041)", async ({ request }) => {
    const body = event();
    expect((await post(request, body)).status()).toBe(202);
    expect((await consumeEventIds(brokers, E2E_EVENTS_TOPIC, [body.event_id])).has(body.event_id)).toBe(true);
  });

  test("session-based ingestion reports the database outage", async ({ context, request }) => {
    await context.addCookies([{ name: "sx_session", value: "A".repeat(43), url: DEGRADED_URL }]);
    const response = await context.request.post("/api/events", {
      data: JSON.stringify(event()),
      headers: { "content-type": "application/json" },
    });
    expect(response.status()).toBe(503);
    expect((await post(request, event(), {})).status()).toBe(401);
  });
});
