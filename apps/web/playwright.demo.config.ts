// Full-stack demo check (Phase 13, D-080): runs against an already running stack, normally
// `docker compose --profile app up -d --build` on http://localhost:3000. No web server is started here.
// Usage: DEMO_EMAIL=... DEMO_PASSWORD=... npx playwright test -c playwright.demo.config.ts
import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./demo-check",
  workers: 1,
  retries: 0,
  forbidOnly: true,
  timeout: 8 * 60_000, // detection plus a live investigation on a CPU-only 3B model
  reporter: [["list"]],
  use: { ...devices["Desktop Chrome"], baseURL: process.env.DEMO_BASE_URL ?? "http://localhost:3000", trace: "retain-on-failure" },
});
