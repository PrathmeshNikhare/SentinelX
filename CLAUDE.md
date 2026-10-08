# SentinelX — Claude Code Project Constitution

## Mission
Build SentinelX, a small but technically credible AI-powered security-log analysis and evidence-based threat investigation platform.

SentinelX is a portfolio/research-grade prototype, NOT an enterprise SIEM/SOC. Favor explainability, deterministic behavior, strong boundaries, testability, and interview-level understanding over feature count.

## Source of truth
The repository is the source of truth. Do not rely on previous chat context.

Before changing code:
1. Read this file.
2. Read `progress/STATUS.md`.
3. Read `progress/DECISIONS.md`.
4. Read `progress/PHASE_LOG.md`.
5. Read `docs/07_PHASES.md`.
6. Read the handoff named in `progress/CURRENT_HANDOFF.md` if one exists.
7. Inspect the actual repository and git status.
8. Run the relevant existing tests before modifying behavior.

## Non-negotiable architecture
Browser -> Next.js App Router -> PostgreSQL / Kafka -> Detection Worker (rules, Isolation Forest, risk, correlation) -> incidents -> FastAPI AI service -> LangGraph -> typed read-only LangChain tools -> Qdrant -> Ollama -> structured validated verdict -> investigation trace -> Next.js incident UI.

Technology:
- Next.js App Router + TypeScript
- Tailwind CSS + shadcn/ui + Recharts
- PostgreSQL + Drizzle ORM
- Apache Kafka
- Python + FastAPI
- pandas + numpy + scikit-learn + Isolation Forest
- LangChain + LangGraph
- Ollama
- Qdrant + sentence-transformers
- Docker Compose
- Vitest + Pytest + Playwright

Do NOT introduce Django, Prisma, Zustand, Kubernetes, Redis, Neo4j, ClickHouse, Elasticsearch/OpenSearch, fine-tuning, cloud-only dependencies, autonomous multi-agent swarms, arbitrary SQL tools, or shell-execution tools for the investigation agent.

## Security model
The LLM does not own the primary numeric risk score.

Detection:
- deterministic rules detect known patterns;
- Isolation Forest provides an anomaly signal;
- deterministic risk engine combines signals into 0–100;
- correlation creates alerts/incidents.

AI:
- retrieves evidence;
- retrieves security knowledge;
- reasons over bounded evidence;
- produces a structured explanation/verdict;
- references evidence IDs;
- suggests defensive recommendations.

The investigation agent is READ-ONLY. It may load incident data, query bounded user history, query bounded IP reputation, query related logs, retrieve MITRE ATT&CK information, and search approved security knowledge.

It may NOT execute shell commands, arbitrary SQL, disable users, block IPs, delete data, change infrastructure, send external messages, or modify security controls.

## Evidence policy
Every material claim in an AI verdict must be traceable to persisted evidence or retrieved security knowledge.

Required verdict shape:
```json
{
  "verdict": "Possible Account Compromise",
  "confidence": 0.93,
  "severity": "HIGH",
  "summary": "Evidence-backed explanation.",
  "evidence_ids": ["ev_1", "ev_2"],
  "mitre_techniques": ["T1110", "T1078"],
  "recommendations": ["Reset credentials", "Revoke active sessions"]
}
```

If evidence references are invalid, unsupported, or missing: reject the verdict, set `requires_review=true`, preserve the invalid result for audit, and never invent evidence.

## UI rules
Build a serious internal security operations console: compact left navigation, dense but readable tables, severity/status badges, event timeline, evidence panels, MITRE ATT&CK references, investigation trace, final verdict and recommendations, meaningful charts only.

Avoid purple gradients, glassmorphism, giant hero sections, glowing text, robot/AI illustrations, decorative 3D/particle effects, generic AI chat interfaces, fake statistics, fake testimonials, and excessive rounded cards.

## Coding rules
- TypeScript strict mode.
- Python type hints.
- Small functions with explicit contracts.
- Validate external input at boundaries.
- Never trust model output without schema validation.
- Never log secrets.
- Use structured logging.
- Use UTC timestamps internally.
- Use IDs for evidence and incidents.
- Do not duplicate business logic across services.
- Prefer readable code over clever abstractions.
- Keep dependencies justified.

## Phase discipline
Never silently skip phases.

A phase may be marked complete only when its acceptance criteria are met, tests pass, security checks pass, documentation is updated, git diff is inspected, a handoff is written, and `progress/STATUS.md` is updated.

The next phase must verify the previous handoff instead of trusting it.

## Handoff discipline
Every phase handoff contains: phase, status, completed work, files changed, tests executed/results, architecture decisions, known issues, deferred work, exact next steps, verification commands, and rollback notes.

Receiving agent procedure:
1. read handoff;
2. inspect git status/diff;
3. run claimed verification;
4. inspect key files;
5. accept (previous phase -> `COMPLETE`) or reject (`REJECTED`);
6. only then start new work.

Phase statuses, gate verdicts and their order are defined in `docs/18_HANDOFF_PROTOCOL.md`.

## Session resume
A new Claude session reconstructs state from repository files. Read `CLAUDE.md`, `STATUS.md`, `DECISIONS.md`, `PHASE_LOG.md`, latest handoff, and actual repository state. Never ask the user to re-explain the project if these files exist.

## First implementation command
Use `/start-phase 00` and follow `docs/07_PHASES.md`.
