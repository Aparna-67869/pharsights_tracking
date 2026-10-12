"use client";

import * as React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Activity,
  BellRing,
  BrainCircuit,
  Building2,
  CalendarClock,
  Database,
  FileSearch,
  FlaskConical,
  Gauge,
  GitCompareArrows,
  LayoutDashboard,
  Network,
  Search,
  ShieldCheck,
  Sparkles,
  X,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useRealtime } from "@/components/providers/realtime-provider";
import { useAuth } from "@/components/providers/auth-provider";

interface NavItem {
  href: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  group: string;
  badge?: string;
  scope?: string;
}

const NAV: NavItem[] = [
  { href: "/", label: "Command Center", icon: LayoutDashboard, group: "Overview" },
  { href: "/alerts", label: "Alerts", icon: BellRing, group: "Overview", badge: "alerts", scope: "read:data" },
  { href: "/ftf", label: "First-to-File", icon: GitCompareArrows, group: "Modules", scope: "read:data" },
  { href: "/pte", label: "Patent Term Ext.", icon: CalendarClock, group: "Modules", scope: "read:data" },
  { href: "/pde", label: "Active Moiety", icon: FlaskConical, group: "Modules", scope: "read:data" },
  { href: "/orange-book", label: "Orange Book", icon: Database, group: "Modules", scope: "read:data" },
  { href: "/changes", label: "Change History", icon: Activity, group: "Modules", scope: "read:data" },
  { href: "/search", label: "Global Search", icon: Search, group: "Intelligence", scope: "read:data" },
  { href: "/graph", label: "Knowledge Graph", icon: Network, group: "Intelligence", scope: "read:data" },
  { href: "/copilot", label: "AI Copilot", icon: BrainCircuit, group: "Intelligence", scope: "use:copilot" },
  { href: "/sources", label: "Sources & Pipeline", icon: FileSearch, group: "Operations", scope: "read:data" },
] as const;

const GROUPS = ["Overview", "Modules", "Intelligence", "Operations"] as const;

export function Sidebar({
  open,
  onClose,
  alertCount,
}: {
  open: boolean;
  onClose: () => void;
  alertCount: number;
}) {
  const pathname = usePathname();
  const { connected } = useRealtime();
  const { hasScope } = useAuth();

  return (
    <>
      {open ? (
        <div
          className="fixed inset-0 z-40 bg-background/70 backdrop-blur-sm lg:hidden"
          onClick={onClose}
        />
      ) : null}
      <aside
        className={cn(
          "fixed inset-y-0 left-0 z-50 flex w-64 flex-col border-r border-border/70 bg-sidebar text-sidebar-foreground transition-transform lg:translate-x-0",
          open ? "translate-x-0" : "-translate-x-full",
        )}
      >
        <div className="flex h-14 items-center justify-between border-b border-white/5 px-4">
          <Link href="/" className="flex items-center gap-2.5" onClick={onClose}>
            <span className="grid h-8 w-8 place-items-center rounded-lg bg-gradient-to-br from-primary to-accent text-primary-foreground shadow-lg shadow-primary/25">
              <ShieldCheck size={18} />
            </span>
            <span className="flex flex-col leading-tight">
              <span className="text-sm font-semibold tracking-tight">Pharma Intel</span>
              <span className="text-[10px] uppercase tracking-wider text-sidebar-foreground/50">
                Command Center
              </span>
            </span>
          </Link>
          <button
            onClick={onClose}
            className="rounded-md p-1.5 text-sidebar-foreground/60 hover:bg-white/10 lg:hidden"
            aria-label="Close navigation"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <nav className="scrollbar-thin flex-1 overflow-y-auto px-3 py-4">
          {GROUPS.map((group) => {
            const items = NAV.filter(
              (item) => item.group === group && (!item.scope || hasScope(item.scope)),
            );
            if (items.length === 0) return null;
            return (
            <div key={group} className="mb-4">
              <p className="px-2 pb-1.5 text-[10px] font-semibold uppercase tracking-wider text-sidebar-foreground/40">
                {group}
              </p>
              <ul className="space-y-0.5">
                {items.map((item) => {
                  const active =
                    item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
                  const Icon = item.icon;
                  return (
                    <li key={item.href}>
                      <Link
                        href={item.href}
                        onClick={onClose}
                        className={cn(
                          "group relative flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm transition-colors",
                          active
                            ? "bg-primary/15 font-medium text-white ring-1 ring-inset ring-primary/30"
                            : "text-sidebar-foreground/70 hover:bg-white/[0.06] hover:text-sidebar-foreground",
                        )}
                      >
                        {active ? (
                          <span className="absolute left-0 top-1/2 h-5 w-[3px] -translate-y-1/2 rounded-r-full bg-primary" />
                        ) : null}
                        <Icon
                          className={cn(
                            "h-4 w-4 transition-colors",
                            active ? "text-primary" : "text-sidebar-foreground/50 group-hover:text-sidebar-foreground/80",
                          )}
                        />
                        <span className="flex-1 truncate">{item.label}</span>
                        {item.badge === "alerts" && alertCount > 0 ? (
                          <span className="rounded-full bg-destructive/25 px-1.5 py-0.5 text-[10px] font-semibold text-destructive-foreground">
                            {alertCount > 99 ? "99+" : alertCount}
                          </span>
                        ) : null}
                      </Link>
                    </li>
                  );
                })}
              </ul>
            </div>
            );
          })}
        </nav>

        <div className="border-t border-white/5 px-4 py-3">
          <div className="flex items-center gap-2 text-[11px] text-sidebar-foreground/60">
            <span
              className={cn(
                "h-2 w-2 rounded-full",
                connected ? "bg-success animate-pulse-ring" : "bg-muted-foreground/50",
              )}
            />
            {connected ? "Live stream connected" : "Reconnecting…"}
          </div>
        </div>
      </aside>
    </>
  );
}

export function Topbar({
  onMenu,
  children,
}: {
  onMenu: () => void;
  children?: React.ReactNode;
}) {
  return (
    <header className="sticky top-0 z-30 flex h-14 items-center gap-3 border-b border-border/70 bg-background/80 px-4 backdrop-blur-xl">
      <button
        onClick={onMenu}
        className="rounded-md p-1.5 text-muted-foreground hover:bg-muted/60 lg:hidden"
        aria-label="Open navigation"
      >
        <Gauge className="h-4 w-4" />
      </button>
      {children}
    </header>
  );
}

export { NAV };
