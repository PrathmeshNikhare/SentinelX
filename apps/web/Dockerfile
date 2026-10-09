# Web console image (D-079). Build context: the repo root (docker compose --profile app build).
# Two stages: the build needs dev dependencies; the runtime installs production dependencies only, so dev-only
# packages (and their advisories, docs/21 10.2) never ship. `npm prune` is avoided: it fails on optional platform
# packages (@tailwindcss/oxide-wasm32-wasi ENOENT).
FROM node:24.11.0-bookworm-slim AS build
ENV NEXT_TELEMETRY_DISABLED=1
WORKDIR /app/apps/web
COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY contracts/ /app/contracts/
COPY fixtures/ /app/fixtures/
COPY apps/web/ ./
RUN npm run build

FROM node:24.11.0-bookworm-slim
ENV NEXT_TELEMETRY_DISABLED=1 NODE_ENV=production
RUN mkdir -p /app/apps/web && chown -R node:node /app
USER node
WORKDIR /app/apps/web
COPY --chown=node:node apps/web/package.json apps/web/package-lock.json ./
RUN npm ci --omit=dev --no-audit --no-fund
COPY --chown=node:node contracts/ /app/contracts/
COPY --chown=node:node fixtures/ /app/fixtures/
COPY --chown=node:node scripts/container-env.sh /app/scripts/container-env.sh
# db:* and demo:send run TypeScript sources with Node's type stripping, so src/ and drizzle/ stay in the image.
COPY --chown=node:node apps/web/ ./
COPY --from=build --chown=node:node /app/apps/web/.next ./.next
EXPOSE 3000
ENTRYPOINT ["sh", "/app/scripts/container-env.sh"]
CMD ["npx", "next", "start", "-H", "0.0.0.0", "-p", "3000"]
