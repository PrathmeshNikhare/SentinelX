# fixtures

Deterministic, synthetic data only (docs/security.md, docs/setup-and-demo.md). No real logs, IPs of real organizations or credentials.

| Content |
|---|
| `ip_reputation.json` (synthetic, RFC 1918/5737 only) and `mitre_techniques.json` (curated ATT&CK subset) — validated by `apps/web/src/db/reference-data.ts`, synced by `npm run db:seed` (D-020, D-032) |
| `scenarios/scenario-{a,b,c}.json` — demo scenarios A/B/C (docs/setup-and-demo.md), validated and expanded by `apps/web/src/demo/scenarios.ts` (D-044) |
| (none) Baseline events for Isolation Forest training are generated in code, seeded and deterministic (`services/detection/sentinelx_detection/baseline.py`, D-049) |
| `knowledge/playbooks.json` — approved defensive playbooks for RAG, written for SentinelX (one document = one retrieval unit, < 1500 characters); ingested with the MITRE techniques by `python -m sentinelx_ai.knowledge` (D-071) |
