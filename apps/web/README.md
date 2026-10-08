# apps/web

Owners (docs/19_AGENT_OWNERSHIP.md): Frontend Engineer (UI), Backend Engineer (server/API boundary), Database Engineer (Drizzle schema in `src/db/`, migrations in `drizzle/`, D-009).

Filled in: Phase 01 (Drizzle schema, migrations, seeds), Phase 02 (Next.js App Router shell, auth), Phase 03 (event API, Kafka producer), Phase 11 (incident UI). Phase 00 provides only the TypeScript toolchain and a smoke test.

Phase 02 adds Next.js to this existing package (`npm install next react react-dom`) rather than running `create-next-app` into a non-empty directory.

## Setup and checks
```sh
npm ci
npm run typecheck   # tsc --noEmit (strict)
npm run lint        # eslint
npm test            # vitest run
```
