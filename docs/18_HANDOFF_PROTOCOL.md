# 18 — Handoff Protocol

States: `IN_PROGRESS`, `READY_FOR_NEXT_PHASE`, `REJECTED`, `BLOCKED`, `COMPLETE`.

Producer writes `progress/handoffs/phase-XX.md` with objective, completed work, files, tests/results, decisions, known issues, deferred work, next-agent requirements, verification and rollback.

Receiver must read the handoff, inspect git status/diff, run verification, inspect key files and accept or reject. If rejected, record the exact failure, fix it and re-verify.

Never accept a handoff merely because the previous agent claims completion.
