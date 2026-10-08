# SentinelX — Claude Code Harness

This is the implementation harness for SentinelX.

## Contains
- `CLAUDE.md` — project constitution.
- `.claude/agents/` — specialized Claude Code agents.
- `.claude/commands/` — repeatable phase/review/handoff workflows.
- `docs/` — authoritative requirements, architecture, security and phases.
- `progress/` — persistent project state and handoffs.

## Install
Copy these files into the root of your SentinelX repository and open Claude Code there.

## First command
```text
/start-phase 00
```

Do not ask Claude to build the whole project at once. Implement one phase at a time: `00 -> 01 -> ... -> 14`.

At the end of each phase use `/verify-phase` and `/handoff`.

At a new session use `/resume`.

The repository is deliberately the source of truth so another Claude session or engineer can continue without chat history.
