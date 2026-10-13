"use client";

import * as React from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";
import { Radio } from "lucide-react";
import { api } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Panel } from "@/components/common/panel";
import { cn } from "@/lib/utils";
import { fmtRelative, PRIORITY_STYLES, moduleLabel } from "@/lib/format";
import { useRealtime } from "@/components/providers/realtime-provider";
import type { Alert } from "@/types/api";

const DOT: Record<string, string> = {
  critical: "bg-destructive",
  high: "bg-warning",
  medium: "bg-primary",
  low: "bg-muted-foreground",
};

/**
 * Datadog-style live event stream. Seeded from the alerts API and then kept
 * current by the websocket: new frames are prepended with a motion transition,
 * so the feed visibly updates without a refresh.
 */
export function LiveAlertStream({ height = 380 }: { height?: number }) {
  const { subscribe, connected } = useRealtime();
  const [live, setLive] = React.useState<Alert[]>([]);

  const { data, isLoading } = useQuery({
    queryKey: ["alerts", "stream"],
    queryFn: () => api.alerts({ page_size: 20, status: "open" }),
    refetchInterval: 45_000,
  });

  React.useEffect(
    () =>
      subscribe((event) => {
        if (!event.topic.startsWith("alert") && !event.event_type?.includes("alert")) return;
        const payload = (event.payload ?? {}) as Record<string, unknown>;
        const incoming: Alert = {
          id: String(payload.alert_id ?? event.event_id ?? Math.random()),
          module: String(payload.module ?? "ftf"),
          event_type: String(event.event_type ?? "regulatory_change"),
          severity: String(payload.priority ?? "medium"),
          title: String(payload.title ?? "New regulatory change detected"),
          priority_score: Number(payload.score ?? 50),
          priority_label: (payload.priority as Alert["priority_label"]) ?? "medium",
          status: "open",
          created_at: event.occurred_at ?? new Date().toISOString(),
        };
        setLive((prev) => [incoming, ...prev].slice(0, 12));
      }),
    [subscribe],
  );

  const merged = React.useMemo(() => {
    const seen = new Set<string>();
    const out: Alert[] = [];
    for (const alert of [...live, ...(data?.items ?? [])]) {
      if (seen.has(alert.id)) continue;
      seen.add(alert.id);
      out.push(alert);
    }
    return out.slice(0, 25);
  }, [live, data]);

  return (
    <Panel
      title="Live event stream"
      subtitle="Detected regulatory changes, newest first"
      icon={<Radio className="h-3.5 w-3.5" />}
      tone="destructive"
      live={connected}
      bodyClassName="p-0"
      actions={
        <Link href="/alerts" className="text-[11px] font-medium text-primary hover:underline">
          Manage
        </Link>
      }
    >
      <div className="scrollbar-thin overflow-y-auto" style={{ height }}>
        {isLoading && merged.length === 0 ? (
          <div className="space-y-2 p-3">
            {Array.from({ length: 5 }).map((_, i) => (
              <div key={i} className="h-12 animate-pulse rounded-lg bg-muted/40" />
            ))}
          </div>
        ) : merged.length === 0 ? (
          <div className="grid h-full place-items-center p-6 text-center">
            <div>
              <p className="text-sm font-medium">Monitoring — no material changes</p>
              <p className="mt-1 text-xs text-muted-foreground">
                Only deltas at or above the alert threshold are published here.
              </p>
            </div>
          </div>
        ) : (
          <AnimatePresence initial={false}>
            {merged.map((alert, index) => {
              const styles = PRIORITY_STYLES[alert.priority_label] ?? PRIORITY_STYLES.low;
              return (
                <motion.div
                  key={alert.id}
                  initial={{ opacity: 0, y: -8 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0 }}
                  transition={{ duration: 0.18 }}
                  className={cn(
                    "group flex gap-2.5 border-b border-border/50 px-3 py-2.5 transition-colors hover:bg-muted/30",
                    index === 0 && live.length > 0 && "bg-primary/[0.06]",
                  )}
                >
                  <span className="mt-1 flex flex-col items-center gap-1">
                    <span className={cn("h-2 w-2 shrink-0 rounded-full", DOT[alert.priority_label] ?? DOT.medium)} />
                    <span className="w-px flex-1 bg-border/60" />
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <Badge className={cn("border px-1.5 py-0 text-[10px]", styles)}>
                        {alert.priority_label.toUpperCase()}
                      </Badge>
                      <span className="text-[10px] uppercase tracking-wide text-muted-foreground">
                        {moduleLabel(alert.module)}
                      </span>
                      <span className="ml-auto shrink-0 text-[10px] text-muted-foreground">
                        {fmtRelative(alert.created_at)}
                      </span>
                    </div>
                    <p className="mt-1 line-clamp-2 text-xs font-medium leading-snug">{alert.title}</p>
                    <div className="mt-0.5 flex items-center gap-2 text-[10px] text-muted-foreground">
                      <span className="font-mono">{alert.event_type}</span>
                      {alert.drug_name ? <span className="truncate">· {alert.drug_name}</span> : null}
                      <Link
                        href="/alerts"
                        className="ml-auto shrink-0 text-primary opacity-0 transition-opacity group-hover:opacity-100"
                      >
                        View details
                      </Link>
                    </div>
                  </div>
                </motion.div>
              );
            })}
          </AnimatePresence>
        )}
      </div>
    </Panel>
  );
}
