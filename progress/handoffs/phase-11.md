# Phase 11 — Incident UI — Handoff

PHASE: 11
STATUS: READY_FOR_NEXT_PHASE
GATE: `/verify-phase` APPROVED (2026-10-09)
BASE COMMIT: `622a9f1` (Phase 10). Phase 11 is the commit that adds this file.
PREVIOUS PHASE: 10 accepted as COMPLETE at the start of this phase (db:roles ok, verify.py 24/24 incl. the live grounded investigation).

## Objective
Timeline, signals, evidence, MITRE, trace, verdict and recommendations. Exit: a complete attack scenario is understandable without source code.

## Completed work
- `/incidents/[id]` rebuilt in the docs/09 order (D-074). The investigation trace sits before evidence, so the reader sees how the evidence was gathered. Sections:
  - header with a "demo scenario data" label;
  - deterministic risk and identity;
  - Summary (facts only);
  - Timeline (rule chips, alert/risk markers);
  - Detection signals (rule reasons, R/A/P/C components and formula);
  - Investigation trace (Investigate button, run status, model/prompt, steps with `llm`/`fallback` origins, inputs, outcomes, evidence links);
  - Evidence (anchored `ev_` rows, source type and ID, claim, "cited in verdict", collapsed source-data preview);
  - MITRE ATT&CK (curated details, "in verdict", links to supporting evidence);
  - Verdict (AI-assessed severity beside the deterministic severity and risk, uncalibrated confidence, summary, cited evidence with claims);
  - Recommendations (marked as suggestions for analyst approval).
- Review, rejected and failed states: a review banner with readable finding labels, detail and attempt; "No accepted verdict"; the failed-run error with evidence kept.
- `src/components/incident/sections.tsx` (server components) and `auto-refresh.tsx`, a client component that calls `router.refresh()` every 4 s while a run is queued or running. Checked against the bundled Next.js 16.3.8 docs.
- `src/lib/investigation-view.ts`: pure labels (findings, effects, actions, source types), defensive parsers for stored verdict and findings JSON, the deterministic summary, duration and JSON preview helpers, technique-to-evidence linking.
- Queries: `getIncident` adds per-event `signals` and the incident's `alerts`; `latestInvestigationDetail`; `getTechniques`.
- `GET /api/incidents/:id` returns the added signals and alerts.

## Files changed
Added:
- `apps/web/src/components/incident/{sections,auto-refresh}.tsx`
- `apps/web/src/lib/{investigation-view,investigation-view.test}.ts`
- `apps/web/e2e/walkthrough.spec.ts`
- `progress/handoffs/phase-11.md`

Modified:
- `apps/web/src/app/(console)/incidents/[id]/page.tsx`
- `apps/web/src/server/queries/{incidents,investigations}.ts`
- `apps/web/README.md`
- `docs/{09_UI_UX_SPEC,14_API_CONTRACTS}.md`
- `progress/{DECISIONS,STATUS,PHASE_LOG,CURRENT_HANDOFF}.md`, `progress/handoffs/phase-10.md` (receiver acceptance)

No AI-service, detection, schema or dependency change.

## Tests executed and results
| Command | Result |
|---|---|
| `python scripts/verify.py` | 24 checks, 0 failed, 0 warnings |
| Web unit (`vitest --project unit`) | 101 passed (7 new: summary facts, the demo label rule, verdict/finding parsers, a label for every AI finding code, duration, JSON preview cut, technique linking) |
| Web E2E (`npm run test:e2e`) | 20 passed, including `walkthrough.spec.ts`: (1) scenario A with a running run that completes while the page is open (auto-refresh), the 8 section headings in order, summary facts, 9 timeline rows with risk markers and rule chips, signal reasons and risk components, 7 trace rows with a fallback badge, 5 evidence rows with "cited in verdict", MITRE linked to evidence, verdict labels, recommendations, evidence anchor navigation; (2) a rejected run → review banner with readable findings and attempt numbers, no verdict, no recommendations |
| Visual review | full-page screenshots from the walkthrough (`apps/web/test-results/…/incident-walkthrough.png`, `incident-review.png`) were reviewed. They showed the risk formula and the trace's evidence links cut off by shadcn's `whitespace-nowrap`; those cells now wrap, confirmed on a new screenshot |
| Mutations (restored byte-identical) | polling disabled → walkthrough fails; review banner shown only while active → review test fails |

## Decisions
D-074 (page structure, labels, review states, polling, no new chart, API additions, the visual review finding).

## Known issues / limitations
- **No live screenshot of a real AI-produced run.** The walkthrough seeds the run as the AI service persists it. The live pipeline that produces such runs is covered by the AI service's live tests (Phases 08–10). Low memory on the reference machine argued against running web, worker, AI service and Ollama together for a manual demo.
- **Width.** The page is desktop-first (docs/09). The dense tables need about 1,280 px; narrower screens scroll horizontally inside the tables.
- **Polling never stops on its own.** It runs while a run stays queued or running, and stops after the AI service's startup abandonment marks a stale run failed (D-065).
- **Source data in the evidence preview is cut at 2,000 characters**; full rows remain in `GET /api/investigations/:id`.
- **Prettier.** It reports style differences in 27 web files (pre-existing). The project's checks are ESLint and tsc, which pass.

## Deferred work
None from Phase 11 scope. Security hardening of the console (headers, rate limits) is Phase 12.

## Next-agent requirements (Phase 12)
1. Verify this handoff and mark Phase 11 `COMPLETE` or `REJECTED`.
2. Phase 12 security and reliability (docs/11, docs/13): auth hardening (login rate limiting, cookie flags in production, security headers/CSP), secrets review (placeholder role passwords, Qdrant without an API key), input-validation audit across the web and AI boundaries, audit logging, dependency review (npm and both Python venvs), failure handling.
3. Carry forward the open hardening items:
   - Qdrant authentication (D-071);
   - the Content-Length-only body cap in the AI service (Phase 06 `ponytail:`);
   - the single-instance assumption for abandoning runs (D-065);
   - the model output lost when validation crashes (Phase 10 known issue).

## Verification commands
```sh
git status                                    # clean
docker compose up -d
(cd apps/web && npm run db:roles)
python scripts/verify.py                      # expect: 24 checks: 0 failed (E2E includes the walkthrough)
(cd apps/web && npx vitest run --project unit)   # expect: 101 passed
(cd apps/web && npx playwright test e2e/walkthrough.spec.ts)  # after `npx next build`; screenshots in test-results/
```

## Rollback
`git revert <phase-11 commit>` restores Phase 10 (`622a9f1`). The changes are UI and read queries only; there is no data or schema change.
