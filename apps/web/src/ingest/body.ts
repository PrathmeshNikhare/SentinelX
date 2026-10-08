// Reads a request body as UTF-8 text with a hard byte limit, without buffering more than the limit
// (a chunked request has no Content-Length to check up front).
export type BodyResult = { ok: true; text: string } | { ok: false; reason: "too_large" };

export async function readBodyLimited(request: Request, maxBytes: number): Promise<BodyResult> {
  const declared = Number(request.headers.get("content-length") ?? "0");
  if (declared > maxBytes) return { ok: false, reason: "too_large" };
  if (!request.body) return { ok: true, text: "" };
  const reader = request.body.getReader();
  const chunks: Uint8Array[] = [];
  let total = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    total += value.byteLength;
    if (total > maxBytes) {
      await reader.cancel();
      return { ok: false, reason: "too_large" };
    }
    chunks.push(value);
  }
  const bytes = new Uint8Array(total);
  let offset = 0;
  for (const chunk of chunks) {
    bytes.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return { ok: true, text: new TextDecoder("utf-8", { fatal: false }).decode(bytes) };
}

export type JsonResult = { ok: true; value: unknown } | { ok: false; reason: "invalid_json" | "forbidden_key" };

/**
 * JSON.parse that rejects a `__proto__` key at any depth. zod 4 silently drops such keys, which is safe but
 * hides tampered input; the boundary rejects it explicitly instead (D-043).
 */
export function parseJsonBody(text: string): JsonResult {
  let forbidden = false;
  let value: unknown;
  try {
    value = JSON.parse(text, (key: string, v: unknown) => {
      if (key === "__proto__") forbidden = true;
      return v;
    });
  } catch {
    return { ok: false, reason: "invalid_json" };
  }
  return forbidden ? { ok: false, reason: "forbidden_key" } : { ok: true, value };
}
