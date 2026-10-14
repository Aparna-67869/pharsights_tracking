"use client";

import * as React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { motion } from "framer-motion";
import { ChevronsLeft, ChevronsRight, X } from "lucide-react";
import { cn } from "@/lib/utils";
import { useRealtime } from "@/components/providers/realtime-provider";
import { useAuth } from "@/components/providers/auth-provider";
import { NAV, NAV_GROUPS } from "@/components/layout/nav-config";
import { BrandLogo, BrandWordmark } from "@/components/common/brand";

/**
 * Collapsible command-center navigation. The collapsed state shows icon-only
 * rails (with tooltips) which is what keeps a 14-item tree usable on a laptop.
 */
export function Sidebar({
  open,
  onClose,
  alertCount,
  collapsed,
  onToggleCollapse,
}: {
  open: boolean;
  onClose: () => void;
  alertCount: number;
  collapsed: boolean;
  onToggleCollapse: () => void;
}) {
  const pathname = usePathname();
  const { connected } = useRealtime();
  const { hasScope, user } = useAuth();

  return (
    <>
      {open ? (
        <div className="fixed inset-0 z-40 bg-background/70 backdrop-blur-sm lg:hidden" onClick={onClose} />
      ) : null}
      <aside
        className={cn(
          "fixed inset-y-0 left-0 z-50 flex flex-col border-r border-border/70 bg-sidebar text-sidebar-foreground transition-[width,transform] duration-200 lg:translate-x-0",
          collapsed ? "w-[62px]" : "w-64",
          open ? "translate-x-0" : "-translate-x-full",
        )}
      >
        <div className={cn("flex h-14 items-center border-b border-white/5", collapsed ? "justify-center px-2" : "justify-between px-4")}>
          <Link href="/" className="flex items-center gap-2.5" onClick={onClose}>
            <BrandLogo className="h-8 w-8" />
            {!collapsed ? (
              <span className="flex flex-col leading-tight">
                <BrandWordmark className="text-sm font-semibold tracking-tight" />
                <span className="text-[10px] uppercase tracking-[0.18em] text-sidebar-foreground/50">
                  Command Center
                </span>
              </span>
            ) : null}
          </Link>
          {!collapsed ? (
            <button
              onClick={onClose}
              className="rounded-md p-1.5 text-sidebar-foreground/60 hover:bg-white/10 lg:hidden"
              aria-label="Close navigation"
            >
              <X className="h-4 w-4" />
            </button>
          ) : null}
        </div>

        <nav className="scrollbar-thin flex-1 overflow-y-auto px-2 py-3">
          {NAV_GROUPS.map((group) => {
            const items = NAV.filter((item) => item.group === group && (!item.scope || hasScope(item.scope)));
            if (items.length === 0) return null;
            return (
              <div key={group} className="mb-3">
                {!collapsed ? (
                  <p className="px-2 pb-1.5 text-[10px] font-semibold uppercase tracking-[0.16em] text-sidebar-foreground/40">
                    {group}
                  </p>
                ) : (
                  <div className="mx-2 mb-2 border-t border-white/5" />
                )}
                <ul className="space-y-0.5">
                  {items.map((item) => {
                    const active = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
                    const Icon = item.icon;
                    return (
                      <li key={item.href}>
                        <Link
                          href={item.href}
                          onClick={onClose}
                          title={collapsed ? item.label : item.hint}
                          className={cn(
                            "group relative flex items-center rounded-lg py-2 text-sm transition-colors",
                            collapsed ? "justify-center px-2" : "gap-2.5 px-2.5",
                            active
                              ? "bg-primary/15 font-medium text-white ring-1 ring-inset ring-primary/30"
                              : "text-sidebar-foreground/70 hover:bg-white/[0.06] hover:text-sidebar-foreground",
                          )}
                        >
                          {active ? (
                            <motion.span
                              layoutId="nav-active"
                              className="absolute left-0 top-1/2 h-5 w-[3px] -translate-y-1/2 rounded-r-full bg-primary"
                            />
                          ) : null}
                          <Icon
                            className={cn(
                              "h-4 w-4 shrink-0 transition-colors",
                              active ? "text-primary" : "text-sidebar-foreground/50 group-hover:text-sidebar-foreground/80",
                            )}
                          />
                          {!collapsed ? (
                            <>
                              <span className="flex-1 truncate">{item.label}</span>
                              {item.badge === "alerts" && alertCount > 0 ? (
                                <span className="rounded-full bg-destructive/25 px-1.5 py-0.5 text-[10px] font-semibold text-white">
                                  {alertCount > 99 ? "99+" : alertCount}
                                </span>
                              ) : null}
                            </>
                          ) : item.badge === "alerts" && alertCount > 0 ? (
                            <span className="absolute right-1.5 top-1.5 h-1.5 w-1.5 rounded-full bg-destructive" />
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

        <div className="border-t border-white/5 p-2">
          {!collapsed ? (
            <div className="flex items-center gap-2 px-2 py-1.5 text-[11px] text-sidebar-foreground/60">
              <span className={cn("live-dot", !connected && "bg-muted-foreground/50")} />
              <span className="flex-1 truncate">{connected ? "Live stream connected" : "Reconnecting…"}</span>
              <span className="truncate text-sidebar-foreground/40">{user?.role?.replace(/_/g, " ")}</span>
            </div>
          ) : null}
          <button
            onClick={onToggleCollapse}
            className="mt-1 hidden w-full items-center justify-center gap-2 rounded-lg py-1.5 text-sidebar-foreground/60 hover:bg-white/[0.06] hover:text-sidebar-foreground lg:flex"
            aria-label={collapsed ? "Expand navigation" : "Collapse navigation"}
          >
            {collapsed ? <ChevronsRight className="h-4 w-4" /> : <ChevronsLeft className="h-4 w-4" />}
            {!collapsed ? <span className="text-[11px]">Collapse</span> : null}
          </button>
        </div>
      </aside>
    </>
  );
}

export { NAV };
