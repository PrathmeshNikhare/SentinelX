# 10 — Coding Standards

TypeScript strict mode; avoid `any`; validate external boundaries; keep server/client separation explicit.

Python type hints; Pydantic/dataclasses for contracts; pure functions where possible; dependency injection for external clients; deterministic tests.

Use explicit names such as `*_id`, `*_at`, `is_*`, `has_*`, `requires_*`.

Expected errors are typed and user-safe. Logs must not expose secrets.

Preferred commits: `feat:`, `fix:`, `test:`, `docs:`, `refactor:`, `security:`. Keep commits reversible.
