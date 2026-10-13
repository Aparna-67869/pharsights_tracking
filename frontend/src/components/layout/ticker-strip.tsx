"use client";

import * as React from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { fmtCompact, fmtNumber } from "@/lib/format";

/**
 * Bloomberg-style ticker strip pinned under the top bar. Each cell is a live
 * metric that links to its module; the strip gives the whole app a market-data
 * feel and keeps the most-watched counts permanently visible.
 */
export function TickerStrip() {
  const { data } = useQuery({
    queryKey: ["kpis"],
    queryFn: () => api.kpis(),
    refetchInterval: 30_000,
  });
  const k = data?.kpis;
  const c = k?.coverage;

  // Real, non-zero corpus counts first — a ticker of zeros reads as a broken
  // feed. The 30-day deltas are only shown when a source has actually moved.
  const cells: Array<{ label: string; value: number; href: string; tone?: string }> = [
    { label: "FTF Records", value: c?.ftf_records ?? 0, href: "/ftf" },
    { label: "PTE Apps", value: c?.pte_applications ?? 0, href: "/pte" },
    { label: "PTE Grants", value: c?.pte_certificates ?? 0, href: "/pte", tone: "text-success" },
    { label: "Active Moieties", value: c?.active_moieties ?? 0, href: "/pde" },
    { label: "Orange Book", value: c?.orange_book_products ?? 0, href: "/orange-book" },
    { label: "Listed Patents", value: c?.listed_patents ?? 0, href: "/patents" },
    { label: "Expiring ≤24m", value: k?.patents_expiring_soon ?? 0, href: "/patents", tone: "text-warning" },
    { label: "Open Alerts", value: k?.open_alerts ?? 0, href: "/alerts", tone: k?.open_alerts ? "text-destructive" : "" },
  ];

  return (
    <div className="ticker-strip scrollbar-thin overflow-x-auto">
      {cells.map((cell) => (
        <Link key={cell.label} href={cell.href} className="ticker-cell group hover:bg-muted/40">
          <span className="whitespace-nowrap text-[10px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">
            {cell.label}
          </span>
          <span className={cn("numeric ml-auto text-sm font-semibold", cell.tone || "text-foreground")}>
            {fmtCompact(cell.value)}
          </span>
        </Link>
      ))}
      <div className="ticker-cell justify-end border-r-0">
        <span className="text-[10px] uppercase tracking-[0.12em] text-muted-foreground">Insights</span>
        <span className="numeric ml-auto text-sm font-semibold text-primary">{fmtNumber(k?.insights_total ?? 0)}</span>
      </div>
    </div>
  );
}
