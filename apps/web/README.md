# apps/web

Owners (docs/19_AGENT_OWNERSHIP.md): Frontend Engineer (UI), Backend Engineer (server/API boundary), Database Engineer (Drizzle schema in `src/db/`, migrations in `drizzle/`, D-009).

Filled in: Phase 01 (schema, migrations, seeds), Phase 02 (console shell, auth, API), Phase 03 (event API, Kafka producer), Phase 11 (incident UI).

## Layout
- `src/app/` — App Router. `login/` (Server Action sign-in), `(console)/` (authenticated layout, overview, incidents, incident detail, events, loading/error states), `api/` (JSON routes).
- `src/proxy.ts` — optimistic cookie check; real session validation happens in every page and API route (D-034).
- `src/server/` — server-only code: `db.ts` (pool as `sentinelx_app`, D-035), `auth/` (scrypt passwords, DB sessions), `queries/`, `api.ts` (401/501/503 helpers), `load.ts` (degraded-state wrapper), `log.ts` (JSON logs, no query parameters).
- `src/components/ui/` — shadcn/ui components; `src/components/console/` — badges, tables, empty/degraded states, sidebar.
- `src/db/` — schema, migrator, seeds, admin CLI (`cli.ts`). `drizzle/` — migrations.
- `src/contracts/` — zod event contracts, source of `contracts/v1/*.schema.json` (D-042). `src/ingest/` — body limits, normalization, ingest token, Kafka producer (D-040–D-043). `src/demo/` — scenario expansion and `send.ts` CLI (D-044).
- `e2e/` — Playwright suite and its throwaway-database setup (D-037).

## Commands
```sh
npm ci
npm run dev            # http://localhost:3000 (sign in with an analyst account)
npm run build && npm run start

npm run typecheck      # next typegen + tsc --noEmit (strict)
npm run lint           # eslint, zero warnings allowed
npm test               # vitest unit project
npm run test:db        # vitest db project (throwaway database)
npm run test:kafka     # vitest kafka project (isolated security-events-test topic)
npm run test:e2e       # next build + Playwright (ports 3100/3101, throwaway sentinelx_e2e database)

npm run db:generate    # new migration after editing src/db/schema.ts (commit it)
npm run db:migrate     # apply migrations (owner DATABASE_URL)
npm run db:seed        # sync reference data from fixtures/
npm run db:roles       # enable LOGIN for sentinelx_app with the APP_DATABASE_URL password
ANALYST_PASSWORD=... npm run analyst:create -- <email> "<name>"

npm run contracts:generate   # regenerate contracts/v1/*.schema.json after editing src/contracts/
npm run demo:send -- A       # post scenario A/B/C to POST /api/events (needs INGEST_API_TOKEN)
```

Scripts under `src/db/` and `e2e/` run with Node 24 type stripping, so relative imports use `.ts` extensions. Do not import `src/db/env.ts` from app code (it would make the bundler include `.env`; D-038).
