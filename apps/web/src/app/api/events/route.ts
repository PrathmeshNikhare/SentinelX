import { notImplemented, withSession } from "@/server/api";

// Event ingestion (validate, publish to Kafka; D-014) is implemented in Phase 03.
export async function POST(): Promise<Response> {
  return withSession("POST /api/events", async () => notImplemented("03"));
}
