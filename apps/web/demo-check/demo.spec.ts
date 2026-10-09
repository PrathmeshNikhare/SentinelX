// The docs/12 scenario A demo end to end on the real stack (docs/08 E2E): ingest -> alert -> incident -> investigate
// -> trace -> evidence references -> verdict. Uses only the browser and the public API, like an analyst.
import { expect, test } from "@playwright/test";
import { expandScenario, loadScenario } from "../src/demo/scenarios.ts";

const email = process.env.DEMO_EMAIL ?? "";
const password = process.env.DEMO_PASSWORD ?? "";

test("scenario A: from ingested events to a grounded verdict", async ({ page }) => {
  test.skip(!email || !password, "set DEMO_EMAIL and DEMO_PASSWORD (an analyst created with npm run analyst:create)");

  await page.goto("/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/$/); // signed in: the overview

  // 1. Ingest: the generator's deterministic scenario, timestamped 10 minutes ago (inside the API's clock-skew bound).
  const events = expandScenario(loadScenario("A"), new Date(Date.now() - 10 * 60_000));
  for (const event of events) {
    const response = await page.request.post("/api/events", { data: event });
    expect(response.status(), event.event_id).toBe(202);
  }
  const firstId = events[0]?.event_id ?? "";

  // 2. Detection: the worker turns the events into an incident that links them (D-052, D-053).
  let incidentId = "";
  await expect(async () => {
    const list = (await (await page.request.get("/api/incidents")).json()) as { incidents: { id: string }[] };
    for (const { id } of list.incidents.slice(0, 20)) {
      const detail = (await (await page.request.get(`/api/incidents/${id}`)).json()) as {
        incident: { events: { externalEventId: string }[] };
      };
      if (detail.incident.events.some((e) => e.externalEventId === firstId)) incidentId = id;
    }
    expect(incidentId).not.toBe("");
  }).toPass({ timeout: 90_000, intervals: [2_000] });

  // 3. The analyst investigates; the page polls until the run finishes (D-015, D-074).
  await page.goto(`/incidents/${incidentId}`);
  await expect(page.getByTestId("risk-score")).not.toHaveText("");
  await page.getByRole("form", { name: "Investigation" }).getByRole("button", { name: "Investigate" }).click();
  await expect(page.getByTestId("latest-investigation")).toContainText(/completed|failed/, { timeout: 6 * 60_000 });
  await expect(page.getByTestId("latest-investigation")).toContainText("completed");

  // 4. Trace, evidence and an accepted, grounded verdict (D-073), or the review banner explaining why not.
  expect(await page.getByTestId("trace").getByRole("row").count()).toBeGreaterThan(4);
  expect(await page.getByTestId("evidence").getByRole("listitem").count()).toBeGreaterThanOrEqual(events.length);
  const verdict = page.getByTestId("verdict");
  if (await verdict.count()) {
    await expect(verdict).toContainText("AI-assessed severity");
    for (const link of await verdict.getByRole("link").all()) {
      const id = (await link.textContent()) ?? "";
      await expect(page.locator(`[id="${id}"]`), `cited ${id} must be an evidence row`).toHaveCount(1);
    }
    await expect(page.getByTestId("recommendations").getByRole("listitem").first()).toBeVisible();
  } else {
    await expect(page.getByTestId("review-banner")).toBeVisible();
  }
  await page.screenshot({ path: test.info().outputPath("demo-incident.png"), fullPage: true });
  console.log(JSON.stringify({ event: "demo.done", incidentId, verdict: (await verdict.count()) > 0 }));
});
