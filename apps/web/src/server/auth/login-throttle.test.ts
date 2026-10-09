import { describe, expect, it } from "vitest";
import { LoginThrottle, MAX_FAILURES, WINDOW_MS } from "./login-throttle.ts";

describe("LoginThrottle (D-075)", () => {
  it("blocks an email after the maximum failures within the window", () => {
    const throttle = new LoginThrottle();
    for (let i = 0; i < MAX_FAILURES; i += 1) {
      expect(throttle.isBlocked("a@x.local", 1000)).toBe(false);
      throttle.recordFailure("a@x.local", 1000 + i);
    }
    expect(throttle.isBlocked("a@x.local", 2000)).toBe(true);
    expect(throttle.isBlocked("b@x.local", 2000)).toBe(false); // other emails are unaffected
  });

  it("unblocks once the window has passed and starts a fresh count", () => {
    const throttle = new LoginThrottle(2, 100);
    throttle.recordFailure("a", 0);
    throttle.recordFailure("a", 10);
    expect(throttle.isBlocked("a", 99)).toBe(true);
    expect(throttle.isBlocked("a", 100)).toBe(false);
    throttle.recordFailure("a", 100);
    expect(throttle.isBlocked("a", 150)).toBe(false);
  });

  it("clears failures after a successful sign-in", () => {
    const throttle = new LoginThrottle(2, WINDOW_MS);
    throttle.recordFailure("a", 0);
    throttle.reset("a");
    throttle.recordFailure("a", 1);
    expect(throttle.isBlocked("a", 2)).toBe(false);
  });

  it("bounds memory when many different emails fail", () => {
    const throttle = new LoginThrottle();
    for (let i = 0; i < 10_050; i += 1) throttle.recordFailure(`user${i}@x.local`, i);
    expect(throttle.size).toBe(10_000);
  });
});
