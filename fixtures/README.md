# fixtures

Deterministic, synthetic data only (docs/11_SECURITY_RULES.md, docs/12_DEMO_SCENARIOS.md). No real logs, IPs of real organizations or credentials.

| Content | Owner | Phase |
|---|---|---|
| `ip_reputation.json` (synthetic, RFC 1918/5737 only) and `mitre_techniques.json` (curated ATT&CK subset) — validated by `apps/web/src/db/reference-data.ts`, synced by `npm run db:seed` (D-020, D-032) | Database Engineer | 01 |
| Demo scenarios A/B/C and baseline events | Detection Engineer | 03–04 |
| Approved security knowledge documents for RAG | AI Agent Engineer | 09 |
