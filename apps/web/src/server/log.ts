// Structured JSON-line logging (CLAUDE.md). Never pass secrets, tokens or passwords in fields.
type Fields = Record<string, string | number | boolean | null | undefined>;

/**
 * Safe summary of an error. Drizzle query errors carry the bound parameters (emails, token hashes,
 * password hashes) in `message` and `params`; only the SQL text and the driver error code are kept.
 */
export function describeError(error: unknown): { message: string; code?: string } {
  if (!(error instanceof Error)) return { message: String(error) };
  const cause = error.cause as { code?: unknown; message?: unknown } | undefined;
  const code = typeof cause?.code === "string" ? cause.code : undefined;
  if ("query" in error && typeof error.query === "string") {
    return { message: `Failed query: ${error.query}`, ...(code ? { code } : {}) };
  }
  const ownCode = (error as { code?: unknown }).code;
  return {
    message: `${error.name}: ${error.message}`,
    ...(typeof ownCode === "string" ? { code: ownCode } : code ? { code } : {}),
  };
}

export function logEvent(event: string, fields: Fields = {}): void {
  console.log(JSON.stringify({ ts: new Date().toISOString(), level: "info", event, ...fields }));
}

export function logError(event: string, error: unknown, fields: Fields = {}): void {
  console.error(JSON.stringify({ ts: new Date().toISOString(), level: "error", event, ...describeError(error), ...fields }));
}
