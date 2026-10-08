// Phase 00 smoke test: guards the CLAUDE.md rule "TypeScript strict mode".
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

interface TsConfig {
  compilerOptions: { strict?: boolean; noUncheckedIndexedAccess?: boolean };
}

const tsconfig = JSON.parse(
  readFileSync(new URL("../tsconfig.json", import.meta.url), "utf8"),
) as TsConfig;

describe("web toolchain", () => {
  it("keeps TypeScript strict mode enabled", () => {
    expect(tsconfig.compilerOptions.strict).toBe(true);
    expect(tsconfig.compilerOptions.noUncheckedIndexedAccess).toBe(true);
  });
});
