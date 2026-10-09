import { describe, expect, it } from "vitest";
import {
  FINDING_LABELS,
  formatDuration,
  parseFindings,
  parseVerdict,
  previewJson,
  summarize,
  techniqueEvidence,
} from "./investigation-view.ts";

const event = (n: number, ip: string, rules: string[], ext = `demo-a-${n}`) => ({
  externalEventId: ext,
  occurredAt: new Date(Date.UTC(2026, 9, 8, 14, 0, n * 20)),
  userId: "alice",
  sourceIp: ip,
  signals: rules.map((ruleName) => ({ ruleName })),
});

describe("summarize", () => {
  it("reports deterministic counts and spans", () => {
    const summary = summarize(
      [event(0, "203.0.113.45", []), event(4, "203.0.113.45", ["brute_force_attempts"]), event(12, "10.10.1.20", ["suspicious_powershell"])],
      [{ riskScore: 72 }, { riskScore: 90 }],
    );
    expect(summary).toMatchObject({
      events: 3,
      durationSeconds: 240,
      users: ["alice"],
      sourceIps: ["203.0.113.45", "10.10.1.20"],
      rules: ["brute_force_attempts", "suspicious_powershell"],
      alerts: 2,
      maxAlertRisk: 90,
      demo: true,
    });
  });

  it("handles an incident without events or alerts and labels only demo-generated data", () => {
    expect(summarize([], [])).toMatchObject({ events: 0, first: null, durationSeconds: 0, maxAlertRisk: null, demo: false });
    expect(summarize([event(0, "192.0.2.10", [], "evt_live_1")], []).demo).toBe(false);
  });
});

describe("parsing stored investigation JSON", () => {
  const verdict = {
    verdict: "Possible Account Compromise",
    confidence: 0.8,
    severity: "HIGH",
    summary: "s",
    evidence_ids: ["ev_0000000000000001"],
    mitre_techniques: ["T1110"],
    recommendations: ["Reset credentials"],
  };

  it("accepts a well-formed verdict and rejects anything else", () => {
    expect(parseVerdict(verdict)).toEqual(verdict);
    expect(parseVerdict(null)).toBeNull();
    expect(parseVerdict({ ...verdict, evidence_ids: "ev_1" })).toBeNull();
    expect(parseVerdict({ ...verdict, confidence: "high" })).toBeNull();
  });

  it("keeps only well-formed findings and labels every code the AI service writes", () => {
    const findings = [
      { attempt: 0, code: "unknown_evidence_id", detail: "evidence_ids[0] ev_ffff", effect: "reject" },
      { code: 3 },
      "nope",
    ];
    expect(parseFindings(findings)).toEqual([findings[0]]);
    expect(parseFindings({})).toEqual([]);
    for (const code of ["schema", "unknown_evidence_id", "unknown_mitre_technique", "unsupported_mitre_technique", "severity_disagreement", "validation_unavailable"]) {
      expect(FINDING_LABELS[code], code).toBeTruthy();
    }
  });
});

describe("display helpers", () => {
  it("formats durations", () => {
    expect([formatDuration(45), formatDuration(240), formatDuration(3720)]).toEqual(["45 s", "4 min 0 s", "1 h 2 min"]);
  });

  it("cuts long JSON previews", () => {
    expect(previewJson({ a: 1 })).toBe('{\n  "a": 1\n}');
    const long = previewJson({ text: "x".repeat(5000) }, 100);
    expect(long.length).toBeLessThan(160);
    expect(long).toContain("more characters");
  });

  it("links techniques to the evidence that mentions them", () => {
    const evidence = [
      { id: "ev_1", sourceType: "mitre", sourceId: "T1110", data: { found: true } },
      { id: "ev_2", sourceType: "knowledge", sourceId: "kd_1", data: { external_id: "T1110", source: "mitre-attack" } },
      { id: "ev_3", sourceType: "knowledge", sourceId: "kd_2", data: { external_id: "pb-x" } },
      { id: "ev_4", sourceType: "event", sourceId: "se_1", data: null },
    ];
    expect(techniqueEvidence("T1110", evidence)).toEqual(["ev_1", "ev_2"]);
    expect(techniqueEvidence("T1078", evidence)).toEqual([]);
  });
});
