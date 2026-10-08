// Used only for `npm run db:generate`; migrations are applied by `npm run db:migrate` (src/db/migrate.ts).
import { defineConfig } from "drizzle-kit";

export default defineConfig({
  dialect: "postgresql",
  schema: "./src/db/schema.ts",
  out: "./drizzle",
});
