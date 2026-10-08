import "server-only";
import { unstable_rethrow } from "next/navigation";
import { logError } from "./log.ts";

export type Loaded<T> = { ok: true; data: T } | { ok: false };

/** Runs a data read; on failure logs it and returns { ok: false } so the view can render a degraded state. */
export async function load<T>(source: string, read: () => Promise<T>): Promise<Loaded<T>> {
  try {
    return { ok: true, data: await read() };
  } catch (error) {
    // Next.js signals dynamic rendering, redirect() and notFound() by throwing; those must propagate.
    unstable_rethrow(error);
    logError("data.unavailable", error, { source });
    return { ok: false };
  }
}
