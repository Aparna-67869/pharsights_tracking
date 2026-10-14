"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import {
  BellRing,
  Check,
  Contrast,
  LogOut,
  Menu,
  Moon,
  RefreshCw,
  Search,
  Sun,
  UserRound,
} from "lucide-react";
import { api } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/components/providers/auth-provider";
import { useTheme } from "@/components/providers/theme-provider";
import { useRealtime } from "@/components/providers/realtime-provider";
import { cn } from "@/lib/utils";
import { fmtRelative } from "@/lib/format";

/**
 * Premium top navigation: brand, universal search, and the operational status
 * cluster (refresh freshness, live connection, theme, alerts, profile).
 */
export function Topbar({
  onMenu,
  onOpenPalette,
  onOpenCopilot,
}: {
  onMenu: () => void;
  onOpenPalette: () => void;
  onOpenCopilot: () => void;
}) {
  const { user, logout } = useAuth();
  const { theme, cycle } = useTheme();
  const { connected, lastEvent } = useRealtime();
  const router = useRouter();
  const [profileOpen, setProfileOpen] = React.useState(false);

  const { data: alertSummary, refetch, isFetching } = useQuery({
    queryKey: ["alert-summary"],
    queryFn: () => api.alertSummary(),
    refetchInterval: 30_000,
  });

  const openAlerts = alertSummary?.open ?? 0;
  const ThemeIcon = theme === "dark" ? Sun : theme === "light" ? Contrast : Moon;

  return (
    <header className="sticky top-0 z-30 flex h-14 items-center gap-2 border-b border-border/70 bg-background/80 px-3 backdrop-blur-xl">
      <button
        onClick={onMenu}
        className="rounded-md p-1.5 text-muted-foreground hover:bg-muted/60 lg:hidden"
        aria-label="Open navigation"
      >
        <Menu className="h-4 w-4" />
      </button>

      <button
        onClick={onOpenPalette}
        className="flex h-9 flex-1 items-center gap-2 rounded-lg border border-border/70 bg-surface/60 px-3 text-sm text-muted-foreground transition-colors hover:bg-surface-muted/60 md:max-w-lg"
      >
        <Search className="h-4 w-4" />
        <span className="flex-1 text-left">Search drugs, patents, NDA/ANDA, sponsors, moieties…</span>
        <kbd className="hidden rounded border border-border bg-muted/60 px-1.5 py-0.5 text-[10px] font-medium md:inline">
          ⌘K
        </kbd>
      </button>

      <div className="ml-auto flex items-center gap-1.5">
        {/* Refresh / freshness */}
        <div className="hidden items-center gap-2 rounded-lg border border-border/70 bg-surface/50 px-2.5 py-1.5 md:flex">
          <RefreshCw className={cn("h-3.5 w-3.5 text-muted-foreground", isFetching && "animate-spin")} />
          <span className="text-[11px] text-muted-foreground">
            {lastEvent ? `updated ${fmtRelative(new Date().toISOString())}` : "auto-refresh 30s"}
          </span>
        </div>

        {/* Connection status */}
        <div className="hidden items-center gap-2 rounded-lg border border-border/70 bg-surface/50 px-2.5 py-1.5 sm:flex">
          <span className={cn("live-dot", !connected && "bg-muted-foreground/50")} />
          <span className={cn("text-[11px] font-medium", connected ? "text-success" : "text-muted-foreground")}>
            {connected ? "Streaming" : "Offline"}
          </span>
        </div>

        <Button variant="ghost" size="icon" onClick={onOpenCopilot} aria-label="Open AI Copilot">
          <span className="grid h-8 w-8 place-items-center rounded-lg bg-primary/12 text-primary ring-1 ring-primary/25">
            <span className="text-[13px] font-bold">AI</span>
          </span>
        </Button>

        <Button variant="ghost" size="icon" onClick={() => router.push("/alerts")} aria-label="Alerts" className="relative">
          <BellRing className="h-4 w-4" />
          {openAlerts > 0 ? (
            <span className="absolute right-1 top-1 grid h-4 min-w-4 place-items-center rounded-full bg-destructive px-1 text-[9px] font-bold text-destructive-foreground">
              {openAlerts > 9 ? "9+" : openAlerts}
            </span>
          ) : null}
        </Button>

        <Button variant="ghost" size="icon" onClick={cycle} aria-label="Toggle theme" title={`Theme: ${theme}`}>
          <ThemeIcon className="h-4 w-4" />
        </Button>

        <div className="relative">
          <button
            onClick={() => setProfileOpen((v) => !v)}
            className="flex items-center gap-2 rounded-lg border border-border/70 bg-surface/60 py-1 pl-2 pr-1.5 transition-colors hover:bg-surface-muted/60"
          >
            <span className="grid h-6 w-6 place-items-center rounded-md bg-gradient-to-br from-primary to-accent text-[11px] font-bold text-primary-foreground">
              {(user?.username ?? "?").slice(0, 1).toUpperCase()}
            </span>
            <span className="hidden flex-col leading-none md:flex">
              <span className="max-w-[130px] truncate text-xs font-medium">{user?.username ?? "—"}</span>
              <span className="text-[10px] uppercase tracking-wide text-muted-foreground">
                {user?.role?.replace(/_/g, " ") ?? ""}
              </span>
            </span>
          </button>

          {profileOpen ? (
            <>
              <div className="fixed inset-0 z-40" onClick={() => setProfileOpen(false)} />
              <div className="absolute right-0 top-11 z-50 w-64 overflow-hidden rounded-xl border border-border/80 bg-panel shadow-glass">
                <div className="border-b border-border/70 p-3">
                  <p className="text-xs text-muted-foreground">Signed in as</p>
                  <p className="truncate text-sm font-medium">{user?.username}</p>
                  <div className="mt-2 flex flex-wrap gap-1">
                    <Badge variant="outline">{user?.role?.replace(/_/g, " ")}</Badge>
                    <Badge variant={connected ? "success" : "secondary"}>{connected ? "live" : "offline"}</Badge>
                  </div>
                </div>
                <div className="p-1">
                  <button
                    onClick={() => {
                      setProfileOpen(false);
                      router.push("/admin");
                    }}
                    className="flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-sm hover:bg-muted/60"
                  >
                    <UserRound className="h-4 w-4" /> Administration
                  </button>
                  <button
                    onClick={() => {
                      setProfileOpen(false);
                      void refetch();
                    }}
                    className="flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-sm hover:bg-muted/60"
                  >
                    <RefreshCw className="h-4 w-4" /> Refresh data now
                  </button>
                  <button
                    onClick={logout}
                    className="flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-sm text-destructive hover:bg-destructive/10"
                  >
                    <LogOut className="h-4 w-4" /> Sign out
                  </button>
                </div>
              </div>
            </>
          ) : null}
        </div>

        <Check className="hidden h-3 w-3 text-success xl:block" aria-hidden />
      </div>
    </header>
  );
}
