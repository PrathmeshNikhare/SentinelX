// Writes contracts/v1/*.schema.json from the zod source (D-042). Usage: npm run contracts:generate
import { writeFileSync } from "node:fs";
import { z } from "zod";
import { normalizedEvent, securityEventInput } from "./security-event.ts";

const CONTRACTS_DIR = new URL("../../../../contracts/v1/", import.meta.url);

/** File name -> exact file content. Shared with the drift test. */
export function renderSchemas(): Record<string, string> {
  const render = (id: string, schema: z.ZodType, io: "input" | "output") =>
    `${JSON.stringify({ $id: id, ...z.toJSONSchema(schema, { target: "draft-2020-12", io }) }, null, 2)}\n`;
  return {
    "security-event.schema.json": render("https://sentinelx.local/contracts/v1/security-event.schema.json", securityEventInput, "input"),
    "normalized-event.schema.json": render(
      "https://sentinelx.local/contracts/v1/normalized-event.schema.json",
      normalizedEvent,
      "output",
    ),
  };
}

export const contractFile = (name: string): URL => new URL(name, CONTRACTS_DIR);

if (import.meta.main) {
  for (const [name, content] of Object.entries(renderSchemas())) {
    writeFileSync(contractFile(name), content, "utf8");
    console.log(JSON.stringify({ event: "contracts.generate", file: `contracts/v1/${name}` }));
  }
}
