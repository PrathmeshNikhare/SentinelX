// Usage: npm run demo:send -- <A|B|C> [--base <ISO timestamp>] [--url <base-url>]
// Posts a deterministic scenario to POST /api/events with INGEST_API_TOKEN (D-044). One JSON log line per event.
import { requireEnv } from "../db/env.ts";
import { defaultBase, expandScenario, isScenarioId, loadScenario, sendEvents } from "./scenarios.ts";

const log = (fields: Record<string, unknown>) => console.log(JSON.stringify({ ts: new Date().toISOString(), ...fields }));

function option(args: string[], name: string): string | undefined {
  const index = args.indexOf(name);
  return index >= 0 ? args[index + 1] : undefined;
}

async function main(args: string[]): Promise<void> {
  const id = args[0]?.toUpperCase() ?? "";
  if (!isScenarioId(id)) throw new Error("usage: npm run demo:send -- <A|B|C> [--base <ISO>] [--url <base-url>]");
  const scenario = loadScenario(id);
  const baseOption = option(args, "--base");
  const base = baseOption ? new Date(baseOption) : defaultBase(scenario, new Date());
  if (Number.isNaN(base.getTime())) throw new Error(`invalid --base "${baseOption ?? ""}"`);
  const url = option(args, "--url") ?? "http://localhost:3000";

  const events = expandScenario(scenario, base);
  log({ event: "demo.start", scenario: scenario.id, name: scenario.name, base: base.toISOString(), events: events.length, url });
  const results = await sendEvents(url, requireEnv("INGEST_API_TOKEN"), events);
  for (const result of results) log({ event: "demo.sent", eventId: result.eventId, status: result.status });
  const failed = results.find((r) => r.status !== 202);
  if (failed) throw new Error(`event ${failed.eventId} rejected with HTTP ${failed.status}: ${JSON.stringify(failed.body)}`);
  log({ event: "demo.done", scenario: scenario.id, accepted: results.length });
}

main(process.argv.slice(2)).catch((error: unknown) => {
  log({ event: "demo.error", message: error instanceof Error ? error.message : String(error) });
  process.exitCode = 1;
});
