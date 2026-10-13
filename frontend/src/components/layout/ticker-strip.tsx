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

  const cells: Array<{ label: string; value: number; href: string; tone?: string }> = [
    { label: "Drugs Monitored", value: k?.drugs_monitored ?? 0, href: "/search" },
    { label: "FTF 30d", value: k?.new_ftf_records ?? 0, href: "/ftf" },
    { label: "PTE Apps 30d", value: k?.new_pte_applications ?? 0, href: "/pte" },
    { label: "PTE Grants 30d", value: k?.new_pte_grants ?? 0, href: "/pte", tone: "text-success" },
    { label: "PDE 30d", value: k?.new_active_moieties ?? 0, href: "/pde" },
    { label: "OB Changes 30d", value: k?.orange_book_updates ?? 0, href: "/orange-book" },
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
