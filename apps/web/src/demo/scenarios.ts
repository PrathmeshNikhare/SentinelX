// Deterministic demo scenarios (D-044, docs/12): fixtures/scenarios/*.json -> API payloads.
import { readFileSync } from "node:fs";
import { z } from "zod";
import { securityEventInput, type SecurityEventInput } from "../contracts/security-event.ts";
import { isSyntheticIp } from "../db/reference-data.ts";

export const SCENARIO_IDS = ["A", "B", "C"] as const;
export type ScenarioId = (typeof SCENARIO_IDS)[number];

const SCENARIOS_DIR = new URL("../../../../fixtures/scenarios/", import.meta.url);

const scenarioEvent = securityEventInput
  .omit({ event_id: true, timestamp: true })
  .extend({ offset_seconds: z.number().int().min(0).max(86_400) })
  .refine((event) => isSyntheticIp(event.source_ip), {
    message: "fixtures may only use RFC 1918 / RFC 5737 addresses (D-032)",
    path: ["source_ip"],
  });

const scenarioFile = z
  .strictObject({
    id: z.enum(SCENARIO_IDS),
    name: z.string().min(1),
    description: z.string().min(1),
    expected: z.string().min(1),
    events: z.array(scenarioEvent).min(1).max(50),
  })
  .refine((s) => s.events.every((e, i) => i === 0 || e.offset_seconds >= (s.events[i - 1]?.offset_seconds ?? 0)), {
    message: "events must be ordered by offset_seconds",
    path: ["events"],
  });

export type Scenario = z.infer<typeof scenarioFile>;

export const isScenarioId = (value: string): value is ScenarioId => (SCENARIO_IDS as readonly string[]).includes(value);

export function parseScenario(raw: unknown): Scenario {
  return scenarioFile.parse(raw);
}

export function loadScenario(id: ScenarioId): Scenario {
  return parseScenario(JSON.parse(readFileSync(new URL(`scenario-${id.toLowerCase()}.json`, SCENARIOS_DIR), "utf8")));
}

/** Base time so the scenario's last event lands at `now` (whole seconds), inside the future-skew window. */
export function defaultBase(scenario: Scenario, now: Date): Date {
  const maxOffset = Math.max(...scenario.events.map((e) => e.offset_seconds));
  return new Date(Math.floor(now.getTime() / 1000) * 1000 - maxOffset * 1000);
}

const compactUtc = (date: Date) => date.toISOString().replace(/\.\d{3}Z$/, "Z").replace(/[-:]/g, "");

/** Same scenario + base -> same events, including event IDs (D-044). Every payload is contract-validated. */
export function expandScenario(scenario: Scenario, base: Date): SecurityEventInput[] {
  const stamp = compactUtc(base);
  return scenario.events.map(({ offset_seconds, ...event }, index) =>
    securityEventInput.parse({
      ...event,
      event_id: `demo-${scenario.id.toLowerCase()}-${stamp}-${String(index + 1).padStart(2, "0")}`,
      timestamp: new Date(base.getTime() + offset_seconds * 1000).toISOString(),
    }),
  );
}

export interface SendResult {
  eventId: string;
  status: number;
  body: unknown;
}

/** Posts events in order to POST /api/events with the ingest token; stops at the first non-202 response. */
export async function sendEvents(
  baseUrl: string,
  token: string,
  events: SecurityEventInput[],
  fetchImpl: typeof fetch = fetch,
): Promise<SendResult[]> {
  const results: SendResult[] = [];
  for (const event of events) {
    const response = await fetchImpl(new URL("/api/events", baseUrl), {
      method: "POST",
      headers: { "content-type": "application/json", authorization: `Bearer ${token}` },
      body: JSON.stringify(event),
    });
    const body: unknown = await response.json().catch(() => null);
    results.push({ eventId: event.event_id, status: response.status, body });
    if (response.status !== 202) break;
  }
  return results;
}
