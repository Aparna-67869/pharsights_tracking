"use client";

import * as React from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Sidebar } from "@/components/layout/sidebar";
import { Topbar } from "@/components/layout/topbar";
import { CopilotDrawer } from "@/components/layout/copilot-drawer";
import { CommandPalette } from "@/components/layout/command-palette";
import { useRealtime } from "@/components/providers/realtime-provider";
import { cn } from "@/lib/utils";

const COLLAPSE_KEY = "pharma.nav.collapsed";

/**
 * Application shell for the command center: collapsible module navigation, the
 * operational top bar, and the global overlays (command palette + floating
 * copilot).
 */
export function AppShell({ children }: { children: React.ReactNode }) {
  const { connected } = useRealtime();
  const [navOpen, setNavOpen] = React.useState(false);
  const [collapsed, setCollapsed] = React.useState(false);
  const [paletteOpen, setPaletteOpen] = React.useState(false);
  const [copilotOpen, setCopilotOpen] = React.useState(false);

  const { data: alertSummary } = useQuery({
    queryKey: ["alert-summary"],
    queryFn: () => api.alertSummary(),
    refetchInterval: 30_000,
  });

  React.useEffect(() => {
    setCollapsed(window.localStorage.getItem(COLLAPSE_KEY) === "1");
  }, []);

  const toggleCollapse = React.useCallback(() => {
    setCollapsed((value) => {
      const next = !value;
      window.localStorage.setItem(COLLAPSE_KEY, next ? "1" : "0");
      return next;
    });
  }, []);

  React.useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const meta = event.metaKey || event.ctrlKey;
      if (meta && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setPaletteOpen((open) => !open);
      }
      // Cmd/Ctrl + J toggles the copilot, matching terminal-app conventions.
      if (meta && event.key.toLowerCase() === "j") {
        event.preventDefault();
        setCopilotOpen((open) => !open);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const openAlerts = alertSummary?.open ?? 0;

  return (
    <div className="min-h-screen bg-background grid-lines">
      <Sidebar
        open={navOpen}
        onClose={() => setNavOpen(false)}
        alertCount={openAlerts}
        collapsed={collapsed}
        onToggleCollapse={toggleCollapse}
      />
      <div className={cn("relative z-10 transition-[padding] duration-200", collapsed ? "lg:pl-[62px]" : "lg:pl-64")}>
        <Topbar
          onMenu={() => setNavOpen(true)}
          onOpenPalette={() => setPaletteOpen(true)}
          onOpenCopilot={() => setCopilotOpen(true)}
        />
        <main className="mx-auto w-full max-w-[1760px] px-3 py-4">{children}</main>
      </div>

      <CommandPalette open={paletteOpen} onOpenChange={setPaletteOpen} />
      <CopilotDrawer open={copilotOpen} onClose={() => setCopilotOpen(false)} />

      {!connected ? (
        <div className="pointer-events-none fixed bottom-4 left-1/2 z-50 -translate-x-1/2 rounded-full border border-border/70 bg-panel/90 px-3 py-1.5 text-[11px] text-muted-foreground shadow-glass backdrop-blur">
          Reconnecting to live stream…
        </div>
      ) : null}
    </div>
  );
}
