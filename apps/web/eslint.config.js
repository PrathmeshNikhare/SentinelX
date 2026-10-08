// Flat config: base JS + strict typescript-eslint + Next.js (core web vitals, TypeScript).
import js from "@eslint/js";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";
import tseslint from "typescript-eslint";

export default tseslint.config(
  { ignores: ["node_modules/", ".next/", "coverage/", "playwright-report/", "test-results/", "next-env.d.ts"] },
  js.configs.recommended,
  ...tseslint.configs.strict,
  ...nextVitals,
  ...nextTs,
  // eslint-plugin-react's version auto-detection calls an API removed in ESLint 10; pin the version instead.
  { settings: { react: { version: "19.3" } } },
);
