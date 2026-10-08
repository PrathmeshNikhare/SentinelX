# Start Phase

Argument: phase number, e.g. `00`.

Read CLAUDE.md, docs/07_PHASES.md, progress/STATUS.md, DECISIONS.md, PHASE_LOG.md and the handoff named in progress/CURRENT_HANDOFF.md. Inspect git status and repository structure. Verify the previous phase's handoff and mark it COMPLETE or REJECTED before starting (Phase 00 has none). Implement only the selected phase unless a blocking dependency requires a documented change. Run tests continuously. At completion, run `/verify-phase`, then `/handoff` only on APPROVED (docs/18_HANDOFF_PROTOCOL.md). Never silently skip a phase.