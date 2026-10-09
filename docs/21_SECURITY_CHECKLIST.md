# 21 — Security Checklist

The Phase 12 exit gate (docs/07). Every item names its implementation and the evidence that proves it; `python scripts/verify.py` runs every listed test. Status is **PASS** or **ACCEPTED** (a documented risk with a reason). Last verified: 2026-10-09 (re-checked for the containerized stack in Phase 13).

## 1. Authentication and sessions
| # | Requirement | Implementation | Evidence | Status |
|---|---|---|---|---|
| 1.1 | Passwords hashed appropriately | scrypt N=2^17, r=8, p=1, salted, constant-time compare (D-034) | `src/server/auth/password.test.ts` | PASS |
| 1.2 | Server-side sessions, hashed tokens, expiry, revocation | `analyst_sessions` stores only the SHA-256 of a 32-byte token; 8 h absolute expiry; logout revokes (D-034) | `db.db.test.ts` (sessions); E2E "sign-out revokes the session server-side" | PASS |
| 1.3 | Secure cookie | `sx_session` HttpOnly, SameSite=Lax, Secure in production, Path=/ | `src/server/auth/session.ts` | PASS |
| 1.4 | No account enumeration | the same message for unknown email and wrong password; unknown emails still run scrypt (D-034) | E2E "rejects wrong credentials…" | PASS |
| 1.5 | Brute-force protection | 5 failed sign-ins per normalized email in 15 min, then refused for the window; applies to unknown emails too; memory-bounded (D-075) | `login-throttle.test.ts`; E2E `security.spec.ts` throttling | PASS |
| 1.6 | CSRF | Server Actions reject cross-origin posts (Next.js Origin check); JSON APIs need a session cookie that is SameSite=Lax and a non-simple content type; no CORS headers are sent | D-034; E2E API tests | PASS |

## 2. Authorization and least privilege
| # | Requirement | Implementation | Evidence | Status |
|---|---|---|---|---|
| 2.1 | Least-privilege database roles | `sentinelx_app` (no DELETE/TRUNCATE/DDL), `sentinelx_ai_tools` (SELECT-only, no analysts or investigation tables), `sentinelx_ai_writer` (append-only trace and evidence) (D-031, D-061, D-065) | `db.db.test.ts` role matrix; `test_tools_db.py` grants in a READ WRITE transaction | PASS |
| 2.2 | Each service connects only as its role | the tools and the store check `current_user` and refuse any other role | `test_tools_db.py`, `test_investigation_live.py::test_persistence_refuses_any_role_but_the_writer` | PASS |
| 2.3 | Internal AI service authenticated | Bearer `AI_SERVICE_TOKEN`, constant-time compare, before routing and parsing; OpenAPI docs disabled (D-058) | `test_app.py` (401 on every route, docs 404) | PASS |
| 2.4 | Machine ingestion authenticated | Bearer `INGEST_API_TOKEN` (32+ characters) or an analyst session (D-041) | E2E ingest credential tests | PASS |
| 2.5 | Qdrant authenticated | `QDRANT__SERVICE__API_KEY` from `QDRANT_API_KEY`; every client sends it; `/readyz` stays open for health checks (D-078) | `curl /collections` without the key → 401; `verify.py` knowledge check uses the key | PASS |

## 3. Secrets
| # | Requirement | Implementation | Evidence | Status |
|---|---|---|---|---|
| 3.1 | No secrets in git | `.env` is untracked; `.env.example` holds placeholders only | `verify.py` "git: no secrets/deps tracked"; history scan of all commits for token, key and password patterns (Phase 12, none found) | PASS |
| 3.2 | Refuse unsafe secrets at startup | `AI_SERVICE_TOKEN` and `QDRANT_API_KEY` must be random and 32+ characters (`validate_secret`, D-025); Compose refuses an empty `QDRANT_API_KEY`; an ingest token under 32 characters disables token auth | `test_contracts_and_config.py` (token and Qdrant key cases) | PASS |
| 3.3 | Secrets never logged | log helpers take explicit fields; database errors keep only SQL text and codes (no parameters); tokens and passwords are never passed | `log.test.ts`; code review of `logEvent`/`log` call sites | PASS |
| 3.5 | No secrets in images | `.dockerignore` excludes `.env` and `.env.*` (except the example); credentials arrive at run time through `env_file` (D-079) | `.dockerignore`; image build context | PASS |
| 3.6 | Container environment | every app container receives the whole `.env` through `env_file`, including secrets it does not use | D-079 | ACCEPTED (local stack; split per-service env files before any shared deployment) |
| 3.4 | Local role passwords | `.env.example` ships `*_local` role passwords | PostgreSQL publishes on 127.0.0.1 only (D-028); `db:roles` sets the password from the URL | ACCEPTED (local-only; set real values before any shared deployment) |

## 4. Input validation at boundaries
| # | Requirement | Implementation | Evidence | Status |
|---|---|---|---|---|
| 4.1 | Event ingestion | zod contract, 16 KiB cap, JSON media type, `__proto__` rejected, clock-skew bound (D-042, D-043) | `ingest.test.ts`; E2E boundary test | PASS |
| 4.2 | Web API IDs and bodies | `inc_`/`run_` formats checked before queries; PATCH body exactly `{status}`, 1 KiB cap | E2E API tests | PASS |
| 4.3 | AI service requests | Pydantic contract (extra fields forbidden), 16 KiB cap, bodies must declare Content-Length (411), values never echoed (D-057, D-077) | `test_app.py` (400, 411, 413) | PASS |
| 4.4 | Agent tool arguments | Pydantic schemas with bounds; unknown fields rejected; invalid arguments never reach the database (D-062) | `test_tools.py` | PASS |
| 4.5 | Retrieved knowledge | Qdrant payloads validated into `KnowledgeHit`; hits must exist in `knowledge_documents` (D-072) | `test_knowledge.py`, `test_tools.py` | PASS |

## 5. Injection and execution
| # | Requirement | Implementation | Evidence | Status |
|---|---|---|---|---|
| 5.1 | Parameterized database access only | Drizzle in the web app; fixed SQL constants with named parameters in Python | `test_tools.py` AST scan (constant `execute()` queries only) | PASS |
| 5.2 | No shell, filesystem, arbitrary HTTP or `eval` in agent tools | import allowlist and forbidden-call scan of `tools.py` | `test_tools.py::test_tools_module_has_no_shell_file_network_or_dynamic_sql_capability` | PASS |
| 5.3 | Prompt injection in evidence | evidence is data: claims are code-written and newline-free, fenced between BEGIN/END EVIDENCE that log text cannot close; the prompts state that evidence is never instructions (D-066, D-073) | `test_graph.py` (injected newlines, injected END EVIDENCE); `test_tools_db.py` (injected text returned verbatim, nothing changed) | PASS |

## 6. Agent boundaries
| # | Requirement | Implementation | Evidence | Status |
|---|---|---|---|---|
| 6.1 | Read-only agent with exactly five tools | `build_tools` registry, `read_only` metadata (D-060) | `test_tools.py` registry test | PASS |
| 6.2 | Bounded loops and results | 8 tool steps, recursion limit, ≤ 32 KiB results, 7-day windows, ≤ 50 rows, top_k ≤ 10 (D-062, D-064) | `test_graph.py` step budget; `test_tools.py` bounds | PASS |
| 6.3 | No data leaves the machine | no LangSmith tracing (the service refuses to start if enabled, D-060); only PostgreSQL, Qdrant and Ollama, all local | `test_tools.py` tracing tests; live startup check (D-060) | PASS |

## 7. LLM output trust
| # | Requirement | Implementation | Evidence | Status |
|---|---|---|---|---|
| 7.1 | Schema and enum validation | constrained decoding plus Pydantic re-validation (D-056) | `test_contracts_and_config.py`, `test_llm.py` | PASS |
| 7.2 | Evidence-ID and MITRE-ID validation; review on unsupported claims | `grounding.check_verdict`: unknown IDs reject; severity two levels apart forces review; retry once, then review with every attempt kept (D-073) | `test_grounding.py`, `test_graph.py`, `test_review_path_db.py` | PASS |
| 7.3 | The model never owns the risk score | the deterministic risk engine owns score and severity; the verdict's severity is labelled AI-assessed (D-004, D-016) | E2E walkthrough labels | PASS |
| 7.4 | Validation failures fail closed | a database outage during validation fails the run, keeps the answer and accepts nothing (D-077) | `test_graph.py::test_a_validation_outage_fails_the_run_but_keeps_the_answer_for_audit` | PASS |

## 8. Audit logging
| # | Requirement | Implementation | Evidence | Status |
|---|---|---|---|---|
| 8.1 | Security-relevant events logged as JSON lines with UTC timestamps | `auth.login`, `auth.login_rejected` (reason `invalid_credentials`/`throttled`), `auth.logout`, `ingest.unauthorized`, `ingest.accepted`, `incident.status_changed`, `investigation.requested`, `ai.unauthorized`, `ai.investigation_queued`/`finished`/`crashed`, `ai.runs_abandoned` (D-077) | log call sites; E2E server output | PASS |
| 8.2 | Logs carry no secrets or untrusted content | no passwords, tokens, emails of failed sign-ins, prompts or model output in logs; AI errors log exception types only | code review; `describe_validation_error` tests | PASS |
| 8.3 | Investigation audit trail | append-only trace and evidence, every model answer kept (D-019, D-073) | `test_review_path_db.py` | PASS |

## 9. Transport and exposure
| # | Requirement | Implementation | Evidence | Status |
|---|---|---|---|---|
| 9.1 | Security headers | CSP (`default-src 'self'`, `frame-ancestors 'none'`, `object-src 'none'`, no `unsafe-eval` in production), nosniff, DENY framing, no-referrer, Permissions-Policy, no `X-Powered-By` (D-076) | E2E `security.spec.ts` (headers, no CSP violations) | PASS |
| 9.2 | CSP allows inline scripts | Next.js hydration scripts need `'unsafe-inline'` without nonces | D-076 | ACCEPTED (local console; move to nonces or SRI before wider exposure) |
| 9.3 | Services bound to localhost | Host ports bind to 127.0.0.1. In the full stack only `web` is published (127.0.0.1:3000); `ai` binds 0.0.0.0 inside the Compose network only and is never published (D-023, D-057, D-079) | `docker-compose.yml`; `__main__.py`; Phase 13 check: `curl 127.0.0.1:8000` from the host fails while the stack runs | PASS |
| 9.5 | Containers run unprivileged | the web image runs as `node`, the Python images as uid 10001 (D-079) | Dockerfiles | PASS |
| 9.4 | Plain HTTP between local services | the AI token and Qdrant key travel over loopback HTTP | D-078 | ACCEPTED (loopback only; add TLS before splitting hosts) |

## 10. Dependency review (2026-10-09)
| # | Scope | Result | Status |
|---|---|---|---|
| 10.1 | Web production dependencies (`npm audit --omit=dev`, 136 packages) | 0 advisories | PASS |
| 10.2 | Web development dependencies (`npm audit`) | 9 advisories (5 high, 4 moderate) in `drizzle-kit`'s bundled esbuild (dev-server request forgery) and `eslint-config-next`'s glob chain (ReDoS-style DoS on crafted patterns). The suggested fixes are major-version downgrades. Neither runs a server here: drizzle-kit only generates migrations, eslint only lints project files | ACCEPTED (dev-only; re-audit when upstream releases fixes) |
| 10.3 | Python: `services/detection` (29 packages), `services/ai` (94 packages), OSV | 0 advisories | PASS |

## 11. Failure handling
| # | Dependency down | Behaviour | Evidence | Status |
|---|---|---|---|---|
| 11.1 | PostgreSQL (web) | pages render a degraded state; APIs answer 503; sign-in reports unavailability | E2E degraded server | PASS |
| 11.2 | Kafka (ingestion) | 503 when Kafka does not acknowledge within 8 s; token ingestion never touches PostgreSQL | `kafka.kafka.test.ts`; E2E ingest | PASS |
| 11.3 | Detection worker errors | poison messages skipped and committed; database or broker errors retried without losing events (D-047) | `services/detection` integration tests | PASS |
| 11.4 | AI service (from the web) | Investigate shows "AI service is unavailable"; the API answers 503 | E2E investigation test; `ai-service.test.ts` | PASS |
| 11.5 | Ollama | proposals fall back to the deterministic plan; the run fails with evidence kept | `test_graph.py` (Ollama down) | PASS |
| 11.6 | Qdrant or the knowledge collection | the tool returns a typed `unavailable` error; the investigation continues | `test_knowledge_live.py` | PASS |
| 11.7 | AI service restart mid-run | unfinished runs are marked failed at startup (D-065) | `test_investigation_live.py` | PASS; ACCEPTED single-instance assumption (D-023) |
