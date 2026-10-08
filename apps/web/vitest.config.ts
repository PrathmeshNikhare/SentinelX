import { defineConfig } from "vitest/config";

// unit: no external services. db: needs the Compose PostgreSQL (DATABASE_URL); creates and drops its own database.
export default defineConfig({
  test: {
    projects: [
      { test: { name: "unit", include: ["src/**/*.test.ts"], exclude: ["src/**/*.db.test.ts"] } },
      { test: { name: "db", include: ["src/**/*.db.test.ts"], testTimeout: 30_000, hookTimeout: 120_000 } },
    ],
  },
});
