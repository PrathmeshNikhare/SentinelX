import { notImplemented, withSession } from "@/server/api";

// Starts an asynchronous investigation (D-015); implemented with the AI service in Phases 06–08.
export async function POST(): Promise<Response> {
  return withSession("POST /api/incidents/:id/investigate", async () => notImplemented("06-08"));
}
