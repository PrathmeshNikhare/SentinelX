"use client";

import { Activity, LayoutDashboard, ShieldAlert } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";

const NAV = [
  { href: "/", label: "Overview", icon: LayoutDashboard },
  { href: "/incidents", label: "Incidents", icon: ShieldAlert },
  { href: "/events", label: "Events", icon: Activity },
] as const;

export function Sidebar() {
  const pathname = usePathname();
  const isActive = (href: string) => (href === "/" ? pathname === "/" : pathname.startsWith(href));
  return (
    <nav aria-label="Primary" className="flex w-48 shrink-0 flex-col border-r bg-sidebar">
      <div className="flex h-12 items-center border-b px-4 font-semibold tracking-tight">SentinelX</div>
      <ul className="flex flex-col gap-0.5 p-2">
        {NAV.map(({ href, label, icon: Icon }) => (
          <li key={href}>
            <Link
              href={href}
              aria-current={isActive(href) ? "page" : undefined}
              className={cn(
                "flex items-center gap-2 rounded-sm px-2 py-1.5 text-sidebar-foreground hover:bg-sidebar-accent",
                isActive(href) && "bg-sidebar-accent font-medium",
              )}
            >
              <Icon className="size-4" aria-hidden />
              {label}
            </Link>
          </li>
        ))}
      </ul>
    </nav>
  );
}
