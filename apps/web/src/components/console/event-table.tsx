import { Mono } from "@/components/console/states";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { formatUtc } from "@/lib/format";

export interface EventRow {
  id: string;
  externalEventId: string;
  occurredAt: Date;
  userId: string;
  sourceIp: string;
  eventType: string;
  action: string;
  resource: string;
  status: string;
}

export function EventTable({ events }: { events: EventRow[] }) {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Time (UTC)</TableHead>
          <TableHead>Event ID</TableHead>
          <TableHead>User</TableHead>
          <TableHead>Source IP</TableHead>
          <TableHead>Type</TableHead>
          <TableHead>Action</TableHead>
          <TableHead>Resource</TableHead>
          <TableHead>Status</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {events.map((event) => (
          <TableRow key={event.id}>
            <TableCell>
              <Mono>{formatUtc(event.occurredAt)}</Mono>
            </TableCell>
            <TableCell>
              <Mono>{event.externalEventId}</Mono>
            </TableCell>
            <TableCell>
              <Mono>{event.userId}</Mono>
            </TableCell>
            <TableCell>
              <Mono>{event.sourceIp}</Mono>
            </TableCell>
            <TableCell>{event.eventType}</TableCell>
            <TableCell>{event.action}</TableCell>
            <TableCell>{event.resource}</TableCell>
            <TableCell>{event.status}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
