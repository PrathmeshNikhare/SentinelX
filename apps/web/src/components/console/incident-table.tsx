import Link from "next/link";
import { SeverityBadge, StatusBadge } from "@/components/console/badges";
import { Mono } from "@/components/console/states";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { formatUtc } from "@/lib/format";
import type { IncidentSummary } from "@/server/queries/incidents";

export function IncidentTable({ incidents }: { incidents: IncidentSummary[] }) {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Incident</TableHead>
          <TableHead>Severity</TableHead>
          <TableHead>Status</TableHead>
          <TableHead className="text-right">Risk</TableHead>
          <TableHead>User</TableHead>
          <TableHead>Source IP</TableHead>
          <TableHead>Updated (UTC)</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {incidents.map((incident) => (
          <TableRow key={incident.id}>
            <TableCell>
              <Link href={`/incidents/${incident.id}`} className="font-medium hover:underline">
                {incident.title}
              </Link>
              <div>
                <Mono>{incident.id}</Mono>
              </div>
            </TableCell>
            <TableCell>
              <SeverityBadge severity={incident.severity} />
            </TableCell>
            <TableCell>
              <StatusBadge status={incident.status} />
            </TableCell>
            <TableCell className="text-right font-mono">{incident.riskScore}</TableCell>
            <TableCell>
              <Mono>{incident.primaryUserId ?? "—"}</Mono>
            </TableCell>
            <TableCell>
              <Mono>{incident.primaryIp ?? "—"}</Mono>
            </TableCell>
            <TableCell>
              <Mono>{formatUtc(incident.updatedAt)}</Mono>
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
