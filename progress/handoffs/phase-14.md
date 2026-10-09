# Phase 14 — Interview Polish — Handoff

PHASE: 14
STATUS: COMPLETE (receiver accepted 2026-10-09 via /resume: no code changed since b67d66e (verify.py 24/24 there); 56/56 decision references exist; 17 component rows complete; Mermaid nodes defined; 16 features and the accepted-risk list match code and docs/21. verify.py was not re-run: the user had just stopped the Docker stack)
GATE: `/verify-phase` APPROVED (2026-10-09)
BASE COMMIT: `b67d66e` (Phase 13). Phase 14 is the commit that adds this file.
PREVIOUS PHASE: 13 accepted as COMPLETE at the start of this phase. verify.py 24/24, and the Phase 13 Compose stack had been running 5 h and serving investigations. The clean-volume demo was not re-run, because it would have meant stopping the user's running stack.

## Objective
Architecture diagram, tradeoffs, performance notes, limitations and interview Q&A. Exit: every major component has a defensible why.

## Completed work
- `docs/02_ARCHITECTURE.md` rewritten as built, in Mermaid:
  - a system and trust-boundary diagram (services, Kafka topic, the three database roles, Qdrant key, host Ollama, the published port);
  - the investigation sequence (202 + polling, LLM proposals with the fallback plan, evidence and trace, grounded validation);
  - a deployment topologies table;
  - the boundaries and contracts.
- `docs/23_INTERVIEW_GUIDE.md`:
  1. a 17-row component table (role, why, cost or rejected alternative, decision references);
  2. key tradeoffs;
  3. measured performance numbers, each with its source;
  4. an honest limitations list;
  5. interview Q&A (13 questions).
- README leads with the one-sentence design summary and links to the architecture, the guide, the security checklist and the demo. docs/17 links to the guide.
- D-081 records how the guide is kept honest: derived from DECISIONS, facts checked against code, updated together with decisions.

## Files changed
Added: `docs/23_INTERVIEW_GUIDE.md`, `progress/handoffs/phase-14.md`.
Modified: `docs/02_ARCHITECTURE.md`, `docs/17_RESEARCH_NOTES.md`, `README.md`, `progress/{DECISIONS,STATUS,PHASE_LOG,CURRENT_HANDOFF}.md`, `progress/handoffs/phase-13.md` (receiver acceptance). No code change.

## Tests executed and results
| Command | Result |
|---|---|
| `python scripts/verify.py` (code identical to `b67d66e`) | 24 checks, 0 failed, 0 warnings |
| Decision-reference check of the guide | 56 cited, all present among 81 decisions |
| Component coverage check | 17 rows with no empty cells; every architecture-diagram component covered |
| Fact checks against code | `FEATURE_NAMES` = 16 (the draft said 15, corrected); 6 ACCEPTED items in docs/21 (the draft said 5, corrected) |
| Mermaid node check | every edge target defined; the `graph` keyword node renamed `lg` |

## Decisions
D-081 (interview documentation and how it stays truthful).

## Known issues / limitations
- **The Mermaid diagrams were checked statically, not rendered locally.** GitHub renders them; a local render needs Mermaid CLI (headless Chromium), which was not run.
- **Performance numbers come from one memory-constrained laptop** (often under 1 GB free) and are indicative only.
- **The project-level limitations stand as listed in docs/23 §4:** synthetic data, a small model, a single node, per-user correlation only, platform-specific model determinism, and the accepted risks.

## Deferred work
None. Phase 14 is the last phase in `docs/07_PHASES.md`. Candidate follow-ups (not scheduled) are listed in docs/23 "What would you do next?": cross-user correlation, a reviewer view of rejected attempts, nonce-based CSP, TLS between services, and confidence calibration.

## Next-agent requirements
1. Verify this handoff and mark Phase 14 `COMPLETE` or `REJECTED` (`/resume` or `/status`).
2. All phases 00–14 are then complete. Further work needs a new phase or decision recorded in `docs/07_PHASES.md` and DECISIONS.md first (CLAUDE.md phase discipline).
3. When any decision changes, update `docs/23_INTERVIEW_GUIDE.md` and `docs/02_ARCHITECTURE.md` in the same change (D-081).

## Verification commands
```sh
git status                                    # clean
python scripts/verify.py                      # expect: 24 checks: 0 failed (infrastructure up, apps/web db:roles run)
# Rendered diagrams: open docs/02_ARCHITECTURE.md on GitHub, or paste the mermaid blocks into https://mermaid.live
```

## Rollback
`git revert <phase-14 commit>` restores Phase 13 (`b67d66e`). Docs only.
