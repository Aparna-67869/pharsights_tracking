"use client";

import * as React from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";
import {
  Activity,
  BellRing,
  ChevronDown,
  ChevronUp,
  CircleDot,
  Loader2,
  RefreshCw,
  Sparkles,
} from "lucide-react";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { fmtNumber, fmtRelative } from "@/lib/format";

/**
 * Bottom status bar: what the platform has actually done today.
 *
 * Figures come from the /activity/today endpoint, which reads real pipeline
 * runs, detected changes, insights and alerts. Expanding the bar shows the
 * newest events (sweeps and material changes) rather than a decorative ticker.
 */
export function ActivityBar() {
  const [expanded, setExpanded] = React.useState(false);
  const { data, isLoading, isFetching, refetch } = useQuery({
    queryKey: ["activity-today"],
    queryFn: () => api.activityToday(),
    refetchInterval: 30_000,
  });

  const sweeps = data?.sweeps;
  const items = data?.items ?? [];

  return (
    <div className="sticky bottom-0 z-30 border-t border-border/70 bg-panel/95 backdrop-blur">
      <AnimatePresence initial={false}>
        {expanded ? (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.18 }}
            className="overflow-hidden border-b border-border/60"
          >
            <div className="scrollbar-thin mx-auto max-h-56 max-w-[1760px] overflow-y-auto px-3 py-2">
              {items.length === 0 ? (
                <p className="py-3 text-center text-[11px] text-muted-foreground">
                  No sweeps recorded today yet. The scheduler runs the collectors automatically.
                </p>
              ) : (
                <ul className="space-y-1">
                  {items.map((item, index) => (
                    <li key={`${item.at}-${index}`} className="flex items-start gap-2 py-0.5 text-[11px]">
                      <CircleDot
                        className={cn(
                          "mt-0.5 h-3 w-3 shrink-0",
                          item.kind === "sweep" ? "text-primary" : "text-warning",
                        )}
                      />
                      <span className="min-w-0 flex-1">
                        <span className="font-medium">{item.title}</span>
                        {item.detail ? <span className="text-muted-foreground"> — {item.detail}</span> : null}
                      </span>
                      <span className="shrink-0 tabular-nums text-muted-foreground">{fmtRelative(item.at)}</span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </motion.div>
        ) : null}
      </AnimatePresence>

      <div className="mx-auto flex max-w-[1760px] flex-wrap items-center gap-x-4 gap-y-1 px-3 py-1.5 text-[11px]">
        <button
          onClick={() => setExpanded((value) => !value)}
          className="inline-flex items-center gap-1.5 font-semibold uppercase tracking-[0.12em] text-muted-foreground hover:text-foreground"
          aria-expanded={expanded}
        >
          <Activity className="h-3.5 w-3.5 text-primary" />
          Today
          {expanded ? <ChevronDown className="h-3 w-3" /> : <ChevronUp className="h-3 w-3" />}
        </button>

        <Stat label="Sweeps" value={sweeps?.runs ?? 0} href="/sources" />
        <Stat
          label="Sources checked"
          value={sweeps?.sources_checked ?? 0}
          href="/sources"
        />
        <Stat
          label="Changes"
          value={data?.changes.material ?? 0}
          tone={(data?.changes.material ?? 0) > 0 ? "text-warning" : undefined}
          href="/intelligence"
        />
        <Stat label="Insights" value={data?.insights ?? 0} href="/intelligence" tone="text-primary" />
        <Stat
          label="Alerts"
          value={data?.alerts.created ?? 0}
          href="/alerts"
          tone={(data?.alerts.open ?? 0) > 0 ? "text-destructive" : undefined}
        />

        <span className="ml-auto flex items-center gap-3">
          <span className="inline-flex items-center gap-1.5 text-muted-foreground">
            <CircleDot
              className={cn(
                "h-3 w-3",
                sweeps?.last_status === "completed"
                  ? "text-success"
                  : sweeps?.last_status
                    ? "text-warning"
                    : "text-muted-foreground/50",
              )}
            />
            {sweeps?.last_at
              ? `Last sweep ${sweeps.last_status?.replace(/_/g, " ")} ${fmtRelative(sweeps.last_at)}`
              : "Awaiting first sweep"}
          </span>
          <Link href="/alerts" className="inline-flex items-center gap-1 text-muted-foreground hover:text-foreground">
            <BellRing className="h-3 w-3" />
            {fmtNumber(data?.alerts.open ?? 0)} open
          </Link>
          <Link href="/intelligence" className="inline-flex items-center gap-1 text-muted-foreground hover:text-foreground">
            <Sparkles className="h-3 w-3" />
            {fmtNumber(data?.insights ?? 0)} insights
          </Link>
          <button
            onClick={() => void refetch()}
            className="inline-flex items-center gap-1 text-muted-foreground hover:text-foreground"
            aria-label="Refresh activity"
          >
            {isFetching || isLoading ? (
              <Loader2 className="h-3 w-3 animate-spin" />
            ) : (
              <RefreshCw className="h-3 w-3" />
            )}
          </button>
        </span>
      </div>
    </div>
  );
}

function Stat({
  label,
  value,
  href,
  tone,
}: {
  label: string;
  value: number;
  href: string;
  tone?: string;
}) {
  return (
    <Link href={href} className="inline-flex items-baseline gap-1.5 hover:opacity-80">
      <span className={cn("numeric text-sm font-semibold tabular-nums", tone ?? "text-foreground")}>
        {fmtNumber(value)}
      </span>
      <span className="text-muted-foreground">{label}</span>
    </Link>
  );
}
