import { describe, expect, it } from "vitest";
import { describeError } from "./log.ts";

// Same shape as drizzle-orm's DrizzleQueryError.
class FakeQueryError extends Error {
  readonly query: string;
  readonly params: unknown[];

  constructor(query: string, params: unknown[], cause: unknown) {
    super(`Failed query: ${query}\nparams: ${params.join(",")}`, { cause });
    this.query = query;
    this.params = params;
  }
}

describe("describeError", () => {
  it("keeps the SQL text and driver code but never the bound parameters", () => {
    const secret = "scrypt$131072$8$1$c2FsdA==$a2V5";
    const error = new FakeQueryError("insert into analysts (password_hash) values ($1)", [secret], {
      code: "ECONNREFUSED",
    });
    const described = describeError(error);
    expect(described).toEqual({ message: "Failed query: insert into analysts (password_hash) values ($1)", code: "ECONNREFUSED" });
    expect(JSON.stringify(described)).not.toContain(secret);
  });

  it("summarizes ordinary errors and non-errors", () => {
    expect(describeError(new TypeError("bad input"))).toEqual({ message: "TypeError: bad input" });
    expect(describeError("plain")).toEqual({ message: "plain" });
  });
});
