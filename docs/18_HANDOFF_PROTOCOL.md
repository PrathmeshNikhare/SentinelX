# 18 — Handoff Protocol

## Phase statuses (STATUS.md, PHASE_LOG.md, handoff files)
- `NOT_STARTED` — no work yet.
- `IN_PROGRESS` — producer is implementing.
- `BLOCKED` — cannot proceed; blocker recorded in STATUS.md.
- `READY_FOR_NEXT_PHASE` — producer's gate returned APPROVED and the handoff is written.
- `COMPLETE` — the receiving agent re-verified the handoff and accepted it.
- `REJECTED` — the receiver (or a gate) found a failure; the exact failure is recorded.

## Gate verdicts (`/verify-phase`, Reviewer agent)
`APPROVED`, `REJECTED`, `BLOCKED`. A verdict is a check result, not a phase status.

## Order
1. Producer implements the phase (`IN_PROGRESS`).
2. Producer runs `/verify-phase`: exit criteria, tests, security, docs, git diff. It does not require a handoff to exist yet.
3. Only on `APPROVED`: producer runs `/handoff`, which writes `progress/handoffs/phase-XX.md`, sets the phase to `READY_FOR_NEXT_PHASE` in STATUS.md and PHASE_LOG.md, and points `progress/CURRENT_HANDOFF.md` at the new file. Then commit.
4. Receiver (next phase or next session) reads the handoff, inspects git status/diff, runs the listed verification and inspects key files.
5. Receiver accepts (previous phase -> `COMPLETE`) or rejects (`REJECTED` with the exact failure, fix, re-verify).

## Handoff contents
`progress/handoffs/phase-XX.md`: phase, status, objective, completed work, files changed, tests/results, decisions, known issues, deferred work, next-agent requirements, verification commands and rollback notes.

Never accept a handoff merely because the previous agent claims completion.
