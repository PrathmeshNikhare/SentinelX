import Link from "next/link";
import { EmptyState } from "@/components/console/states";

export default function IncidentNotFound() {
  return (
    <EmptyState title="Incident not found">
      It may not exist or the link is malformed.{" "}
      <Link href="/incidents" className="underline">
        Back to incidents
      </Link>
    </EmptyState>
  );
}
