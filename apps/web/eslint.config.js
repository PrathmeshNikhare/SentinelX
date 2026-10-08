// Flat config. Phase 02 extends this with the Next.js rules when the app is added.
import js from "@eslint/js";
import tseslint from "typescript-eslint";

export default tseslint.config(
  { ignores: ["node_modules/", ".next/", "coverage/"] },
  js.configs.recommended,
  ...tseslint.configs.strict,
);
