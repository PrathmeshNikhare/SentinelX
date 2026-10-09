#!/bin/sh
# Entrypoint for the app containers (D-079). The repo-root .env holds host addresses (localhost:<port>); inside the
# Compose network PostgreSQL is postgres:5432. Rewrite only the host:port of the database URLs so the credentials in
# .env stay the single source of truth, then run the command. Usage: container-env.sh <command> [args...]
set -eu

for name in DATABASE_URL APP_DATABASE_URL AI_TOOLS_DATABASE_URL AI_WRITER_DATABASE_URL; do
  eval "value=\${$name:-}"
  if [ -n "$value" ]; then
    rewritten=$(printf '%s' "$value" | sed -E 's#@(localhost|127\.0\.0\.1):[0-9]+/#@postgres:5432/#')
    export "$name=$rewritten"
  fi
done

exec "$@"
