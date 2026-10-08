import { defineConfig } from "vitest/config";

// unit: no external services. db: Compose PostgreSQL (throwaway database). kafka: Compose Kafka (own test topic).
export default defineConfig({
  test: {
    projects: [
      { test: { name: "unit", include: ["src/**/*.test.ts"], exclude: ["src/**/*.db.test.ts", "src/**/*.kafka.test.ts"] } },
      { test: { name: "db", include: ["src/**/*.db.test.ts"], testTimeout: 30_000, hookTimeout: 120_000 } },
      { test: { name: "kafka", include: ["src/**/*.kafka.test.ts"], testTimeout: 60_000, hookTimeout: 60_000 } },
    ],
  },
});
