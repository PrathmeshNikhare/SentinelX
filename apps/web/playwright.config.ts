// E2E against a production build (D-037). `npm run test:e2e` builds first, then starts two servers:
// healthy (3100, throwaway sentinelx_e2e database) and degraded (3101, unreachable database, Kafka reachable).
// Both publish to the isolated `security-events-e2e` topic.
import { defineConfig, devices } from "@playwright/test";
import { DEGRADED_URL, E2E_EVENTS_TOPIC, E2E_INGEST_TOKEN, HEALTHY_URL, e2eAppUrl, unreachableAppUrl } from "./e2e/support.ts";

const ingestEnv = { INGEST_API_TOKEN: E2E_INGEST_TOKEN, KAFKA_EVENTS_TOPIC: E2E_EVENTS_TOPIC };

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  forbidOnly: true,
  reporter: [["list"]],
  globalTeardown: "./e2e/global-teardown.ts",
  use: { ...devices["Desktop Chrome"], baseURL: HEALTHY_URL, trace: "retain-on-failure" },
  webServer: [
    {
      command: "node e2e/prepare-db.ts && npx next start --port 3100",
      url: `${HEALTHY_URL}/login`,
      env: { APP_DATABASE_URL: e2eAppUrl(), ...ingestEnv },
      reuseExistingServer: false,
      timeout: 180_000,
    },
    {
      command: "npx next start --port 3101",
      url: `${DEGRADED_URL}/login`,
      env: { APP_DATABASE_URL: unreachableAppUrl(), ...ingestEnv },
      reuseExistingServer: false,
      timeout: 180_000,
    },
  ],
});
