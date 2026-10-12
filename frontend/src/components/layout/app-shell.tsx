"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { BellRing, LogOut, Moon, Search, Sparkles, Sun, UserRound } from "lucide-react";
import { api } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Sidebar, Topbar } from "@/components/layout/sidebar";
import { CommandPalette } from "@/components/layout/command-palette";
import { useAuth } from "@/components/providers/auth-provider";
import { useTheme } from "@/components/providers/theme-provider";
import { useRealtime } from "@/components/providers/realtime-provider";

export function AppShell({ children }: { children: React.ReactNode }) {
  const { user, logout } = useAuth();
  const { theme, toggle } = useTheme();
  const { connected } = useRealtime();
  const router = useRouter();
  const [navOpen, setNavOpen] = React.useState(false);
  const [paletteOpen, setPaletteOpen] = React.useState(false);

  const { data: alertSummary } = useQuery({
    queryKey: ["alert-summary"],
    queryFn: () => api.alertSummary(),
    refetchInterval: 30_000,
  });

  React.useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setPaletteOpen((open) => !open);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const openAlerts = alertSummary?.open ?? 0;

  return (
    <div className="min-h-screen bg-background">
      <Sidebar open={navOpen} onClose={() => setNavOpen(false)} alertCount={openAlerts} />
      <div className="lg:pl-64">
        <Topbar onMenu={() => setNavOpen(true)}>
          <button
            onClick={() => setPaletteOpen(true)}
            className="flex h-9 flex-1 items-center gap-2 rounded-lg border border-border/70 bg-surface/60 px-3 text-sm text-muted-foreground transition-colors hover:bg-surface-muted/60 md:max-w-md"
          >
            <Search className="h-4 w-4" />
            <span className="flex-1 text-left">Search drugs, patents, NDA/ANDA, sponsors…</span>
            <kbd className="hidden rounded border border-border bg-muted/60 px-1.5 py-0.5 text-[10px] font-medium md:inline">
              ⌘K
            </kbd>
          </button>

          <div className="ml-auto flex items-center gap-1.5">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => router.push("/copilot")}
              className="hidden sm:inline-flex"
            >
              <Sparkles className="h-4 w-4 text-primary" />
              Copilot
            </Button>
            <Button variant="ghost" size="icon" onClick={() => router.push("/alerts")} aria-label="Alerts">
              <span className="relative">
                <BellRing className="h-4 w-4" />
                {openAlerts > 0 ? (
                  <span className="absolute -right-1 -top-1 grid h-3.5 min-w-3.5 place-items-center rounded-full bg-destructive px-0.5 text-[9px] font-bold text-destructive-foreground">
                    {openAlerts > 9 ? "9+" : openAlerts}
                  </span>
                ) : null}
              </span>
            </Button>
            <Button variant="ghost" size="icon" onClick={toggle} aria-label="Toggle theme">
              {theme === "dark" ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
            </Button>

            <div className="ml-1 hidden items-center gap-2 rounded-lg border border-border/70 bg-surface/60 py-1 pl-2 pr-1 md:flex">
              <UserRound className="h-4 w-4 text-muted-foreground" />
              <div className="flex flex-col leading-none">
                <span className="max-w-[140px] truncate text-xs font-medium">
                  {user?.username ?? "—"}
                </span>
                <span className="text-[10px] uppercase tracking-wide text-muted-foreground">
                  {user?.role?.replace(/_/g, " ") ?? ""}
                </span>
              </div>
              <Badge variant={connected ? "success" : "secondary"} className="ml-1">
                {connected ? "live" : "offline"}
              </Badge>
              <Button variant="ghost" size="icon" onClick={logout} aria-label="Sign out">
                <LogOut className="h-4 w-4" />
              </Button>
            </div>
          </div>
        </Topbar>

        <main className="mx-auto w-full max-w-[1700px] px-4 py-5">{children}</main>
      </div>

      <CommandPalette open={paletteOpen} onOpenChange={setPaletteOpen} />
    </div>
  );
}
