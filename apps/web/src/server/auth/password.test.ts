import { describe, expect, it } from "vitest";
import { hashPassword, MIN_PASSWORD_LENGTH, passwordPolicyError, verifyPassword } from "./password.ts";

const PASSWORD = "correct horse battery staple";

describe("password hashing", { timeout: 30_000 }, () => {
  it("produces a salted scrypt hash that verifies only the right password", async () => {
    const stored = await hashPassword(PASSWORD);
    expect(stored).toMatch(/^scrypt\$131072\$8\$1\$[A-Za-z0-9+/=]{24}\$[A-Za-z0-9+/=]{44}$/);
    expect(await verifyPassword(PASSWORD, stored)).toBe(true);
    expect(await verifyPassword(`${PASSWORD}!`, stored)).toBe(false);
    expect(await hashPassword(PASSWORD)).not.toBe(stored); // random salt
  });

  it("normalizes Unicode so visually identical passwords match", async () => {
    const stored = await hashPassword("pässword-1234");
    expect(await verifyPassword("pässword-1234", stored)).toBe(true);
  });

  it.each([
    ["empty", ""],
    ["wrong scheme", "bcrypt$131072$8$1$c2FsdA==$a2V5"],
    ["missing parts", "scrypt$131072$8$1$c2FsdA=="],
    ["extra parts", "scrypt$131072$8$1$c2FsdA==$a2V5$x"],
    ["non power-of-two N", "scrypt$100000$8$1$c2FsdHNhbHRzYWx0c2FsdA==$" + "A".repeat(43) + "="],
    ["N above the bound", `scrypt$${2 ** 21}$8$1$c2FsdHNhbHRzYWx0c2FsdA==$` + "A".repeat(43) + "="],
    ["short key", "scrypt$131072$8$1$c2FsdHNhbHRzYWx0c2FsdA==$a2V5"],
  ])("rejects a malformed stored hash (%s) without throwing", async (_label, stored) => {
    expect(await verifyPassword(PASSWORD, stored)).toBe(false);
  });

  it("enforces the length policy", async () => {
    expect(passwordPolicyError("x".repeat(MIN_PASSWORD_LENGTH - 1))).toMatch(/at least/);
    expect(passwordPolicyError("x".repeat(MIN_PASSWORD_LENGTH))).toBeNull();
    expect(passwordPolicyError("x".repeat(1025))).toMatch(/at most/);
    await expect(hashPassword("short")).rejects.toThrow(/at least/);
    expect(await verifyPassword("x".repeat(1025), await hashPassword(PASSWORD))).toBe(false);
  });
});
