import { readFileSync } from "node:fs";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { contractFile } from "../contracts/generate.ts";
import { investigationAccepted, investigationRequest } from "../contracts/investigation.ts";
import { startInvestigation } from "./ai-service.ts";

vi.mock("server-only", () => ({}));

const INCIDENT = "inc_3f9a2b1c4d5e6f70";
const ANALYST = "an_bf897b6605224d78";
const TOKEN = "test-ai-service-token-0123456789abcdef";
const example = (name: string): unknown => JSON.parse(readFileSync(contractFile(`examples/${name}`), "utf8"));
const reply = (status: number, body: unknown) =>
  vi.fn<typeof fetch>(async () => new Response(JSON.stringify(body), { status }));

describe("AI contracts on the web side (D-011, D-059)", () => {
  it("parses the shared examples", () => {
    expect(investigationRequest.parse(example("investigation-request.json"))).toBeTruthy();
    expect(investigationAccepted.parse(example("investigation-accepted.json"))).toBeTruthy();
  });

  it("rejects extra fields and malformed IDs", () => {
    expect(investigationAccepted.safeParse({ investigation_run_id: "run_x", status: "queued" }).success).toBe(false);
    const extra = { investigation_run_id: "run_0a1b2c3d4e5f6a7b", status: "queued", verdict: {} };
    expect(investigationAccepted.safeParse(extra).success).toBe(false);
  });
});

describe("startInvestigation", () => {
  beforeEach(() => {
    vi.stubEnv("AI_SERVICE_URL", "http://127.0.0.1:8000");
    vi.stubEnv("AI_SERVICE_TOKEN", TOKEN);
    vi.spyOn(console, "error").mockImplementation(() => undefined);
  });
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.restoreAllMocks();
  });

  it("sends the contract body with the service token and returns the run id", async () => {
    const fetchMock = reply(202, { investigation_run_id: "run_0a1b2c3d4e5f6a7b", status: "queued" });
    expect(await startInvestigation(INCIDENT, ANALYST, fetchMock)).toEqual({ ok: true, runId: "run_0a1b2c3d4e5f6a7b" });
    const [url, init] = fetchMock.mock.calls[0] ?? [];
    expect(String(url)).toBe("http://127.0.0.1:8000/v1/investigations");
    expect(init?.method).toBe("POST");
    expect(init?.redirect).toBe("error");
    expect(init?.headers).toEqual({ authorization: `Bearer ${TOKEN}`, "content-type": "application/json" });
    expect(JSON.parse(String(init?.body))).toEqual({ incident_id: INCIDENT, requested_by: ANALYST });
  });

  it.each([
    [404, { error: { code: "not_found" } }, "not_found"],
    [409, { error: { code: "investigation_in_progress" } }, "in_progress"],
    [401, { error: { code: "unauthorized" } }, "unavailable"],
    [503, { error: { code: "unavailable" } }, "unavailable"],
    [202, { investigation_run_id: "not-a-run", status: "queued" }, "unavailable"], // contract violation
  ])("maps HTTP %i to %s", async (status, body, reason) => {
    expect(await startInvestigation(INCIDENT, ANALYST, reply(status, body))).toEqual({ ok: false, reason });
  });

  it("treats a network failure or timeout as unavailable", async () => {
    const failing = vi.fn<typeof fetch>(async () => {
      throw new DOMException("The operation timed out.", "TimeoutError");
    });
    expect(await startInvestigation(INCIDENT, ANALYST, failing)).toEqual({ ok: false, reason: "unavailable" });
  });

  it.each([
    ["AI_SERVICE_TOKEN", ""],
    ["AI_SERVICE_TOKEN", "too-short"],
    ["AI_SERVICE_URL", ""],
  ])("does not call the service when %s is %j", async (name, value) => {
    vi.stubEnv(name, value);
    const fetchMock = reply(202, {});
    expect(await startInvestigation(INCIDENT, ANALYST, fetchMock)).toEqual({ ok: false, reason: "unavailable" });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("refuses malformed IDs before any request", async () => {
    const fetchMock = reply(202, {});
    await expect(startInvestigation("inc_bad", ANALYST, fetchMock)).rejects.toThrow();
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
