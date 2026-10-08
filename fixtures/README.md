# fixtures

Deterministic, synthetic data only (docs/11_SECURITY_RULES.md, docs/12_DEMO_SCENARIOS.md). No real logs, IPs of real organizations or credentials.

| Content | Owner | Phase |
|---|---|---|
| `ip_reputation.json` (synthetic, RFC 1918/5737 only) and `mitre_techniques.json` (curated ATT&CK subset) — validated by `apps/web/src/db/reference-data.ts`, synced by `npm run db:seed` (D-020, D-032) | Database Engineer | 01 |
| `scenarios/scenario-{a,b,c}.json` — demo scenarios A/B/C (docs/12), validated and expanded by `apps/web/src/demo/scenarios.ts` (D-044) | Detection Engineer | 03 |
| (none) Baseline events for Isolation Forest training are generated in code, seeded and deterministic (`services/detection/sentinelx_detection/baseline.py`, D-049) | Detection Engineer | 04 |
| Approved security knowledge documents for RAG | AI Agent Engineer | 09 |
