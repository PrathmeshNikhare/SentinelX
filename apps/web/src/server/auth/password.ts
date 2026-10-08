// Password hashing with Node's built-in scrypt (D-034). Stored format: scrypt$N$r$p$saltB64$keyB64.
import { randomBytes, scrypt, timingSafeEqual } from "node:crypto";

export const MIN_PASSWORD_LENGTH = 12;
export const MAX_PASSWORD_LENGTH = 1024;

const COST = { N: 2 ** 17, r: 8, p: 1 } as const;
const KEY_LENGTH = 32;
const SALT_LENGTH = 16;
const MAX_N = 2 ** 20; // bounds parameters read back from storage
const maxmem = (N: number, r: number) => 256 * N * r; // scrypt needs ~128*N*r bytes

function deriveKey(password: string, salt: Buffer, N: number, r: number, p: number): Promise<Buffer> {
  return new Promise((resolve, reject) => {
    scrypt(password.normalize("NFKC"), salt, KEY_LENGTH, { N, r, p, maxmem: maxmem(N, r) }, (error, key) =>
      error ? reject(error) : resolve(key),
    );
  });
}

export function passwordPolicyError(password: string): string | null {
  if (password.length < MIN_PASSWORD_LENGTH) return `Password must be at least ${MIN_PASSWORD_LENGTH} characters.`;
  if (password.length > MAX_PASSWORD_LENGTH) return `Password must be at most ${MAX_PASSWORD_LENGTH} characters.`;
  return null;
}

export async function hashPassword(password: string): Promise<string> {
  const policyError = passwordPolicyError(password);
  if (policyError) throw new Error(policyError);
  const salt = randomBytes(SALT_LENGTH);
  const key = await deriveKey(password, salt, COST.N, COST.r, COST.p);
  return ["scrypt", COST.N, COST.r, COST.p, salt.toString("base64"), key.toString("base64")].join("$");
}

const isPowerOfTwo = (n: number) => Number.isInteger(n) && n > 1 && (n & (n - 1)) === 0;

/** Constant-time check. Malformed or out-of-bounds stored hashes return false instead of throwing. */
export async function verifyPassword(password: string, stored: string): Promise<boolean> {
  if (password.length > MAX_PASSWORD_LENGTH) return false;
  const [scheme, nText, rText, pText, saltB64, keyB64, ...rest] = stored.split("$");
  if (scheme !== "scrypt" || !saltB64 || !keyB64 || rest.length > 0) return false;
  const N = Number(nText);
  const r = Number(rText);
  const p = Number(pText);
  if (!isPowerOfTwo(N) || N > MAX_N || !Number.isInteger(r) || r < 1 || r > 32 || !Number.isInteger(p) || p < 1 || p > 16) {
    return false;
  }
  const expected = Buffer.from(keyB64, "base64");
  if (expected.length !== KEY_LENGTH) return false;
  const actual = await deriveKey(password, Buffer.from(saltB64, "base64"), N, r, p);
  return timingSafeEqual(actual, expected);
}

let dummyHash: Promise<string> | undefined;

/** A real hash to compare against when the account does not exist, so timing does not reveal valid emails. */
export function dummyPasswordHash(): Promise<string> {
  dummyHash ??= hashPassword("sentinelx-dummy-password-for-timing");
  return dummyHash;
}
