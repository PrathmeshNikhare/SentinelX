import type { Metadata } from "next";
import { EventTable } from "@/components/console/event-table";
import { DataUnavailable, EmptyState, PageHeader } from "@/components/console/states";
import { requireSession } from "@/server/auth/session";
import { load } from "@/server/load";
import { listRecentEvents } from "@/server/queries/events";

export const metadata: Metadata = { title: "Events" };

export default async function EventsPage() {
  if (!(await requireSession())) return <DataUnavailable what="Events" />;
  const events = await load("events", () => listRecentEvents());
  return (
    <>
      <PageHeader title="Events" description="Most recent persisted security events (latest 100)." />
      {!events.ok ? (
        <DataUnavailable what="Events" />
      ) : events.data.length === 0 ? (
        <EmptyState title="No security events">Events appear here once they are ingested and processed.</EmptyState>
      ) : (
        <EventTable events={events.data} />
      )}
    </>
  );
}
