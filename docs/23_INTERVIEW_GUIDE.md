# 23 — Interview Guide: Why, Tradeoffs, Performance, Limitations

How SentinelX is built and why, in a form you can defend in an interview. Every claim points to a decision in `progress/DECISIONS.md` (D-nnn) or a measured result. The system diagram is in `docs/02_ARCHITECTURE.md`.

**One sentence.** Deterministic code detects, scores and correlates. A small local LLM only investigates: it gathers evidence through read-only tools and explains it, and code rejects any verdict that cites something the investigation did not actually retrieve.

## 1. Every major component and why it is there
| Component | Role | Why this | What it costs / what was rejected | Decisions |
|---|---|---|---|---|
| Next.js App Router (TypeScript) | Console, session boundary, user-facing APIs | Server components read PostgreSQL directly with typed queries, so there is no separate BFF. Server Actions get Next's built-in cross-origin rejection, which covers CSRF for forms | Hydration needs inline scripts (CSP `'unsafe-inline'`, accepted locally). A separate SPA plus API was not needed for one console | D-001, D-034–D-036, D-074, D-076 |
| PostgreSQL + Drizzle | The single source of truth: events, signals, alerts, incidents, runs, trace, evidence, reference data | Relational integrity (FKs, unique keys) makes idempotency and append-only audit enforceable by the database. Drizzle migrations are the only DDL; Python uses plain psycopg with fixed SQL | Two languages read the same schema without an ORM in Python (deliberate: one DDL owner) | D-010, D-014, D-030, D-031 |
| Kafka (KRaft, single node) | Decouples ingestion from detection | The API only validates and publishes, so ingestion survives a slow or down detector and a backlog can be replayed. Keying by `user_id` keeps per-user order, which correlation needs | Operationally heavier than a queue table. A single broker means no HA, which is fine for a laptop | D-003, D-014, D-040, D-045, D-047 |
| Deterministic rules | Known patterns: brute force, login after failures, new or risky IP, encoded PowerShell, sensitive files, privilege change, impossible travel, post-compromise chain | Explainable, testable and reproducible; each signal carries its reason. Evaluated at event time against history strictly before the event, so replay gives identical results | Only catches what was written down; thresholds are judgment calls documented per rule | D-048 |
| Isolation Forest | Anomaly signal (0–1) over 16 documented features | Unsupervised: no labelled attacks needed; cheap to train (seconds) and score. Trained deterministically on a seeded synthetic baseline; each alert stores the model version | Synthetic baseline, so prototype-grade realism. Deterministic per platform only (the Linux and Windows builds score scenario A at 88 vs 90). Never the final risk on its own | D-013, D-049, D-079 |
| Deterministic risk engine | One 0–100 score: `0.45·rule + 0.25·anomaly + 0.15·IP reputation + 0.15·correlation` | Auditable and reproducible: alerts store the components and the formula, and the UI shows them. The weights were traced against the three demo scenarios before being fixed | Hand-tuned weights, not learned. The LLM may never compute or override it | D-004, D-050 |
| Correlation → incidents | Group a user's activity into incidents (60-minute event-time window) | Event time only, so replays are deterministic. Incidents never merge or split; resolved incidents are never reopened by detection | No cross-user correlation yet (e.g. password spraying across users) | D-053, D-054, D-055 |
| FastAPI AI service | Owns investigations: graph, tools, retrieval, LLM adapter, validation, trace | The Python ML/agent ecosystem. An internal-only service with a bearer token checked before routing; docs endpoints disabled; not published in Compose | One more process and contract; justified by the language boundary (detection and AI are Python, the console is TypeScript) | D-002, D-022, D-057, D-058 |
| LangGraph investigation | `load_incident → analyze → choose action → run tool → store evidence → … → build verdict → validate` | An explicit, bounded state machine (8 tool steps, recursion limit) instead of a free-running agent. Every step is traced. The LLM only proposes; invalid, duplicate or unavailable proposals fall back to a deterministic plan | A 3B model repeats actions after about 4 steps, so the fallback fills the budget. Autonomous multi-agent swarms were ruled out by the constitution | D-015, D-017, D-064 |
| Typed read-only tools (LangChain `StructuredTool`) | User history, IP reputation, related logs, MITRE lookup, knowledge search | Pydantic schemas double as the LLM's action schema and the validation boundary. Fixed SELECTs under a SELECT-only role in read-only sessions; bounded windows, rows and bytes; an AST test forbids shell, HTTP, eval and dynamic SQL | LangChain adds `langsmith`, so cloud tracing is refused at startup. `langchain-ollama` was rejected: one thin httpx adapter is easier to bound and test | D-005, D-060–D-063, D-067 |
| Ollama + `llama3.2:3b` | Local inference for action proposals and the verdict | Local-first: no data leaves the machine. Runs on a laptop. Constrained JSON-schema decoding plus Pydantic re-validation | Small model: invents MITRE IDs and miscounts (hence D-073). Not bit-reproducible even at temperature 0. Numeric bounds are not enforced by the decoder | D-007, D-056, D-068 |
| Qdrant + `all-MiniLM-L6-v2` | Semantic retrieval of approved knowledge (curated MITRE + playbooks) | Retrieved knowledge becomes evidence with a real `kd_` source ID, checked against `knowledge_documents`. A small CPU embedding model (384-d, about 0.1 s per query); model pinned to a Hub commit, baked into the image | A second datastore. pgvector would have avoided it; the stack names Qdrant, and Elasticsearch/OpenSearch are excluded by the constitution | D-006, D-070–D-072 |
| Evidence-grounded validation | Gate between the model and the analyst | Rejects unknown evidence IDs, unknown or unretrieved MITRE IDs, and invented IDs in the prose; retries once naming the failures; forces review when severity is two or more levels from the deterministic one; keeps every answer for audit | Proves that references are real, not that every sentence is true; review and evidence panels are the human check | D-016, D-019, D-073 |
| Least-privilege roles | `sentinelx_app`, `sentinelx_ai_tools` (SELECT-only), `sentinelx_ai_writer` (append-only trace and evidence) | A compromised or confused agent cannot write, delete or read password hashes. Each service checks `current_user` and refuses any other role | Three passwords to manage (local placeholders accepted for 127.0.0.1-only) | D-022, D-031, D-061, D-065 |
| Versioned contracts (`contracts/v1`) | Event, investigation request/accepted and verdict schemas | One owner per contract (zod for events, Pydantic for AI) generates JSON Schema; drift tests on both sides | Generation step plus drift test per contract | D-011, D-042, D-059 |
| Docker Compose | Infrastructure for development; the whole stack for demos | One command, local-only ports, fresh-volume start in 73 s; non-root images; `.env` stays the single credential source | No orchestration or HA (Kubernetes ruled out by the constitution); Ollama stays on the host for GPU access | D-023, D-079, D-080 |
| `verify.py` + Vitest/Pytest/Playwright | The phase gate | One stdlib entrypoint runs lint, type checks, unit, DB/Kafka integration, live LLM/Qdrant tests and E2E against a production build (24 checks) | Slow (about 10 minutes) because it is real; live-model tests can fail on model nondeterminism, and the review path covers that in production | D-024, D-037, D-080 |

## 2. Key tradeoffs
- **Determinism where it matters, LLM where it helps.** Detection, scoring and correlation are pure code and reproducible. The LLM's output is advisory, labelled ("AI-assessed", "uncalibrated"), and can only cite what was retrieved. Cost: the LLM cannot discover what the rules miss, by design.
- **Read-only agent.** No remediation tools exist to misuse. Recommendations are text for a human to approve. Cost: no automated containment.
- **Fallback plan over agent freedom.** An invalid or unavailable LLM never stalls an investigation, because a deterministic plan for the incident runs instead and every step records its origin (`llm`/`fallback`).
- **Reject, don't repair, model output.** Out-of-range confidence or invented IDs are rejected and retried with the failed fields named, never silently clamped or edited.
- **Append-only audit.** Trace and evidence rows can only be inserted (grants), and every model answer, valid or not, is stored. Cost: storage grows with every run.
- **Local-first security.** Everything binds to 127.0.0.1, the AI service is unpublished, and secrets are refused when weak. Accepted local risks are listed in docs/21 (CSP inline scripts, loopback HTTP, whole `.env` per container).
- **Small, pinned dependencies.** Day-old releases are skipped, OSV/npm audits are recorded, and dev-only advisories never ship (multi-stage web image).

## 3. Performance notes (measured on the reference laptop, CPU-only, 16 GB RAM, often under 1 GB free)
| What | Measured | Source |
|---|---|---|
| Ollama, `llama3.2:3b` | cold call 40.5 s (11 s model load), warm call 5–7 s | D-056 |
| One investigation (≤ 8 tool steps plus the verdict) | 49–78 s typical, 113 s under memory pressure | D-064, D-068, D-073, D-080 |
| Embedding model | cold load 19–40 s (torch import), then about 0.1 s per query | D-070 |
| Qdrant via `localhost` on Windows | +2 s per call; fixed with IPv4 (`127.0.0.1`) | D-070 |
| psycopg via `localhost` on Windows | 90 s stall; fixed with `hostaddr=127.0.0.1` and a 10 s connect timeout | D-051 |
| Live retrieval tests | 103 s → 46 s after the IPv4 and lazy-client fixes | D-070 |
| Isolation Forest training | about 3.5 s (deterministic, done at image build) | D-049, D-079 |
| Full stack from empty volumes | 73 s to all services up; demo end to end 1.8 min | D-080 |
| Images | AI 2.28 GB, web 1.55 GB, detection 0.61 GB | D-079 |

Where time goes: investigations are LLM-bound (about 9 sequential model calls). Detection and retrieval are milliseconds to sub-second. A GPU or a smaller action-selection prompt would cut the investigation time the most.

## 4. Limitations (honest list)
- **Synthetic data:** synthetic events, baseline and IP reputation; the knowledge corpus is 19 documents (11 curated techniques, 8 playbooks).
- **Small local model:** prone to repetition and miscounts. Grounding checks references, not the truth of each sentence.
- **Single-node scope:** single broker, single AI instance (startup abandonment and the login throttle assume one instance), no HA.
- **Correlation:** per user only (no cross-user spraying detection). Impossible travel needs `metadata.geo`.
- **Determinism:** the anomaly model is deterministic per platform, not across platforms. LLM output is near-deterministic, not reproducible.
- **Accepted security risks:** the 6 ACCEPTED items in docs/21 (local role passwords, whole `.env` per container, CSP inline scripts, loopback HTTP, dev-only npm advisories, single-instance restart handling).
- **Not built:** SIEM connectors, remediation, multi-tenant auth, Kubernetes or cloud deployment, fine-tuning (all out of scope per docs/01).

## 5. Interview Q&A
**Why not let the LLM compute the risk score?** It is not reproducible, not auditable and can be talked into anything by log content. The score is a documented formula over rule, anomaly, reputation and correlation inputs, stored with its components (D-004, D-050). The model's severity is shown separately, and a two-level disagreement forces review (D-016).

**How do you stop the LLM from inventing evidence?** Evidence rows are written by code with code-written claims, and the model sees only those IDs. After generation, every cited `ev_` ID must belong to this run, and every MITRE ID must be curated and retrieved in this run, including IDs inside the prose. Otherwise the verdict is rejected and retried once with the failures named; if it fails again, it goes to review with every attempt stored (D-073).

**What about prompt injection in logs?** Logs are data. Fields are clipped and newline-collapsed into one-line claims, so injected text cannot forge an evidence line. The evidence block is fenced and log text cannot close the fence (tested). The tools are read-only, under a SELECT-only role, and cannot shell out, make HTTP calls or build SQL. Even a fully hijacked model can only produce a verdict, which is then validated (D-066, D-073, docs/21 §5).

**Why Kafka instead of writing events straight to PostgreSQL?** The API stays fast and available when detection is slow or down, events can be replayed (D-055), and per-user ordering comes from the message key. Idempotency lives in the worker (`ON CONFLICT DO NOTHING` on the external event ID, D-014).

**Why Isolation Forest?** No labelled attacks are needed, it is fast, and it is an anomaly signal rather than a verdict: one weighted input to the risk score (25 %). Its features are documented, its training is deterministic, and its version is stored with every alert (D-049).

**Why LangGraph if a fallback plan exists anyway?** The graph makes the loop explicit and bounded, and the LLM can still adapt the order and arguments of actions. The fallback guarantees progress when the model is wrong or down. The trace shows which origin chose each step (D-017, D-064).

**Why a 3B local model?** Local-first: no data leaves the machine, and it runs on a laptop. Validation is designed for a weak model, so a stronger model would only improve the pass rate (D-056).

**How is the agent kept safe?** Five tools, each with an input schema, bounds, a timeout and a result size cap, under a SELECT-only database role. A static test forbids dangerous imports and calls. There are no write or remediation tools at all (D-060–D-062).

**How do you know RAG results are real sources?** Each hit carries the `kd_` ID of a stored document and is checked against `knowledge_documents`; points without a valid reference are dropped. The exit test asserts expected source IDs for five paraphrased queries (D-071, D-072).

**What happens when Ollama, Qdrant or the database is down?** Ollama: the fallback plan runs, then the run fails with its evidence kept. Qdrant: the tool returns a typed error and the investigation continues. Database: the console renders degraded states and validation fails closed. Each case is tested (docs/21 §11).

**How would you scale this?**
- Partition Kafka by user and run several detection workers in one consumer group (ordering per key is preserved).
- Move the login throttle and run ownership into PostgreSQL so the web and AI tiers can run several instances.
- Use a GPU or a hosted model behind the same adapter interface.
- Add IP-keyed correlation.

The contracts and role boundaries already support splitting services.

**What would you do next?** Cross-user correlation, a reviewer view of rejected attempts, nonce-based CSP, TLS between services, and calibrating the model's confidence against analyst outcomes.

**What did you learn?**
- Small models need code around them: schemas, grounding, retries that say what failed.
- Windows `localhost` resolving to IPv6 first cost seconds in three different clients.
- A test harness must be robust to the same resource pressure as production; the poll timeout fix came from exactly that (D-080).
