# Create Handoff

Only after `/verify-phase` returned APPROVED for this phase. Create `progress/handoffs/phase-XX.md` with phase/status, objective, completed work, files changed, exact tests/results, decisions, known issues, deferred work, next-agent requirements, verification commands and rollback. Set the phase to `READY_FOR_NEXT_PHASE` in `progress/STATUS.md` and `progress/PHASE_LOG.md`, and point `progress/CURRENT_HANDOFF.md` at the new file. See `docs/18_HANDOFF_PROTOCOL.md`.
