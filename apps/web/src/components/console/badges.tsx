import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

// Text labels always carry the meaning; colour is secondary (accessibility).
const SEVERITY_STYLES: Record<string, string> = {
  LOW: "border-slate-300 bg-slate-100 text-slate-700",
  MEDIUM: "border-amber-300 bg-amber-50 text-amber-800",
  HIGH: "border-orange-300 bg-orange-50 text-orange-800",
  CRITICAL: "border-red-300 bg-red-50 text-red-800",
};

const STATUS_STYLES: Record<string, string> = {
  open: "border-sky-300 bg-sky-50 text-sky-800",
  investigating: "border-yellow-300 bg-yellow-50 text-yellow-800",
  resolved: "border-emerald-300 bg-emerald-50 text-emerald-800",
};

const base = "rounded-sm px-1.5 py-0 font-mono text-[11px] font-semibold uppercase tracking-wide";

export function SeverityBadge({ severity }: { severity: string }) {
  return (
    <Badge variant="outline" className={cn(base, SEVERITY_STYLES[severity])}>
      {severity}
    </Badge>
  );
}

export function StatusBadge({ status }: { status: string }) {
  return (
    <Badge variant="outline" className={cn(base, STATUS_STYLES[status])}>
      {status}
    </Badge>
  );
}
