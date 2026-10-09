// Login throttling (D-075): after 5 failed sign-ins for one email within 15 minutes, further attempts for that email
// are refused until the window passes. Applies to unknown emails too, so it reveals nothing about which accounts exist.
// ponytail: in-process memory, correct for the single web instance (D-023); a multi-instance deployment needs a shared
// store (e.g. a PostgreSQL table) and a per-client-IP limit behind a trusted proxy.

export const MAX_FAILURES = 5;
export const WINDOW_MS = 15 * 60 * 1000;
const MAX_TRACKED = 10_000; // bounds memory when an attacker sprays many emails

interface Entry {
  failures: number;
  windowStart: number;
}

export class LoginThrottle {
  private readonly entries = new Map<string, Entry>();
  private readonly maxFailures: number;
  private readonly windowMs: number;

  constructor(maxFailures = MAX_FAILURES, windowMs = WINDOW_MS) {
    this.maxFailures = maxFailures;
    this.windowMs = windowMs;
  }

  private current(key: string, now: number): Entry | undefined {
    const entry = this.entries.get(key);
    if (entry && now - entry.windowStart >= this.windowMs) {
      this.entries.delete(key);
      return undefined;
    }
    return entry;
  }

  /** True when this email has used up its failed attempts for the current window. */
  isBlocked(key: string, now = Date.now()): boolean {
    return (this.current(key, now)?.failures ?? 0) >= this.maxFailures;
  }

  recordFailure(key: string, now = Date.now()): void {
    const entry = this.current(key, now);
    if (entry) {
      entry.failures += 1;
      return;
    }
    if (this.entries.size >= MAX_TRACKED) {
      const oldest = this.entries.keys().next().value; // Map keeps insertion order
      if (oldest !== undefined) this.entries.delete(oldest);
    }
    this.entries.set(key, { failures: 1, windowStart: now });
  }

  /** A successful sign-in clears the email's failures. */
  reset(key: string): void {
    this.entries.delete(key);
  }

  get size(): number {
    return this.entries.size;
  }
}

export const loginThrottle = new LoginThrottle();
