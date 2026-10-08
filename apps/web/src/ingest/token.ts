// Bearer-token check for non-browser event producers such as the demo generator (D-041).
import { createHash, timingSafeEqual } from "node:crypto";

export const MIN_INGEST_TOKEN_LENGTH = 32;

export type TokenCheck = "valid" | "invalid" | "disabled" | "misconfigured";

const digest = (value: string) => createHash("sha256").update(value).digest();

/**
 * Compares a presented token with the configured one in constant time (equal-length SHA-256 digests).
 * An empty configured token disables token auth; one shorter than the minimum is refused as misconfigured.
 */
export function checkIngestToken(presented: string, configured: string | undefined): TokenCheck {
  if (!configured) return "disabled";
  if (configured.length < MIN_INGEST_TOKEN_LENGTH) return "misconfigured";
  return timingSafeEqual(digest(presented), digest(configured)) ? "valid" : "invalid";
}

/** The token from an `Authorization: Bearer <token>` header, or null. */
export function bearerToken(authorization: string | null): string | null {
  const match = authorization ? /^Bearer ([^\s]+)$/.exec(authorization) : null;
  return match?.[1] ?? null;
}
