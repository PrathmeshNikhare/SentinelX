import { notImplemented, withSession } from "@/server/api";

// Investigation status, verdict and trace (D-015); implemented in Phases 06–08.
export async function GET(): Promise<Response> {
  return withSession("GET /api/investigations/:id", async () => notImplemented("06-08"));
}
