import type { Metadata } from "next";
import { IncidentTable } from "@/components/console/incident-table";
import { DataUnavailable, EmptyState, PageHeader } from "@/components/console/states";
import { requireSession } from "@/server/auth/session";
import { load } from "@/server/load";
import { listIncidents } from "@/server/queries/incidents";

export const metadata: Metadata = { title: "Incidents" };

export default async function IncidentsPage() {
  if (!(await requireSession())) return <DataUnavailable what="Incidents" />;
  const incidents = await load("incidents", () => listIncidents());
  return (
    <>
      <PageHeader title="Incidents" description="Correlated incidents, most recently updated first (latest 100)." />
      {!incidents.ok ? (
        <DataUnavailable what="Incidents" />
      ) : incidents.data.length === 0 ? (
        <EmptyState title="No incidents">Incidents appear here when the detection pipeline correlates alerts.</EmptyState>
      ) : (
        <IncidentTable incidents={incidents.data} />
      )}
    </>
  );
}
