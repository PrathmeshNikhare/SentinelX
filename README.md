# SentinelX — Claude Code Harness

This is the implementation harness for SentinelX.

## Contains
- `CLAUDE.md` — project constitution.
- `.claude/agents/` — specialized Claude Code agents.
- `.claude/commands/` — repeatable phase/review/handoff workflows.
- `docs/` — authoritative requirements, architecture, security and phases.
- `progress/` — persistent project state and handoffs.

## Repository
This directory is the SentinelX repository (D-008). Open Claude Code here.

## First command
```text
/start-phase 00
```

Do not ask Claude to build the whole project at once. Implement one phase at a time: `00 -> 01 -> ... -> 14`.

At the end of each phase use `/verify-phase`, then `/handoff` only if it returns APPROVED (`docs/18_HANDOFF_PROTOCOL.md`).

At a new session use `/resume`.

The repository is deliberately the source of truth so another Claude session or engineer can continue without chat history.
