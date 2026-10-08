import { describe, expect, it } from "vitest";
import { canTransition, INCIDENT_TRANSITIONS, isIncidentStatus, sourcesFor } from "./incident-lifecycle.ts";

describe("incident lifecycle (D-054)", () => {
  it("allows exactly the documented transitions", () => {
    const allowed = Object.entries(INCIDENT_TRANSITIONS).flatMap(([from, tos]) => tos.map((to) => `${from}->${to}`));
    expect(allowed.sort()).toEqual(
      ["open->investigating", "open->resolved", "investigating->open", "investigating->resolved", "resolved->open"].sort(),
    );
    expect(canTransition("resolved", "investigating")).toBe(false);
    expect(canTransition("open", "open")).toBe(false);
  });

  it("derives the guard of the conditional update", () => {
    expect(sourcesFor("resolved").sort()).toEqual(["investigating", "open"]);
    expect(sourcesFor("open").sort()).toEqual(["investigating", "resolved"]);
    expect(sourcesFor("investigating")).toEqual(["open"]);
  });

  it("validates untrusted status values", () => {
    expect(isIncidentStatus("resolved")).toBe(true);
    expect(isIncidentStatus("RESOLVED")).toBe(false);
    expect(isIncidentStatus(undefined)).toBe(false);
    expect(isIncidentStatus(["open"])).toBe(false);
  });
});
