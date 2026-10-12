"use client";

import * as React from "react";
import { ArrowDownRight, ArrowUpRight, Minus } from "lucide-react";
import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import { fmtCompact } from "@/lib/format";

export function KpiCard({
  label,
  value,
  hint,
  icon,
  tone = "default",
  trend,
  onClick,
}: {
  label: string;
  value: number | string;
  hint?: string;
  icon?: React.ReactNode;
  tone?: "default" | "primary" | "success" | "warning" | "destructive";
  trend?: number | null;
  onClick?: () => void;
}) {
  const toneRing: Record<string, string> = {
    default: "text-muted-foreground bg-muted/50 ring-border/70",
    primary: "text-primary bg-primary/12 ring-primary/25",
    success: "text-success bg-success/12 ring-success/25 dark:text-emerald-300",
    warning: "text-warning-foreground bg-warning/12 ring-warning/30 dark:text-amber-300",
    destructive: "text-destructive bg-destructive/12 ring-destructive/25 dark:text-red-300",
  };

  const toneRail: Record<string, string> = {
    default: "hsl(var(--muted-foreground))",
    primary: "hsl(var(--primary))",
    success: "hsl(var(--success))",
    warning: "hsl(var(--warning))",
    destructive: "hsl(var(--destructive))",
  };

  return (
    <Card
      className={cn(
        "rail group relative overflow-hidden p-4 transition-all duration-200",
        onClick && "cursor-pointer hover:-translate-y-0.5 hover:shadow-glass hover:ring-1 hover:ring-primary/30",
      )}
      style={{ ["--rail-color" as string]: toneRail[tone] }}
      onClick={onClick}
    >
      <div
        className="pointer-events-none absolute inset-0 opacity-0 transition-opacity duration-200 group-hover:opacity-100"
        style={{
          background: `radial-gradient(14rem 8rem at 100% 0%, ${toneRail[tone]}1f, transparent 70%)`,
        }}
      />
      <div className="relative flex items-start justify-between gap-3">
        <p className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
          {label}
        </p>
        {icon ? (
          <span className={cn("grid h-8 w-8 place-items-center rounded-lg ring-1", toneRing[tone])}>
            {icon}
          </span>
        ) : null}
      </div>
      <div className="relative mt-2 flex items-end gap-2">
        <span className="stat-number">
          {typeof value === "number" ? fmtCompact(value) : value}
        </span>
        {typeof trend === "number" ? (
          <span
            className={cn(
              "mb-0.5 inline-flex items-center gap-0.5 text-[11px] font-medium",
              trend > 0 ? "text-success" : trend < 0 ? "text-destructive" : "text-muted-foreground",
            )}
          >
            {trend > 0 ? (
              <ArrowUpRight className="h-3 w-3" />
            ) : trend < 0 ? (
              <ArrowDownRight className="h-3 w-3" />
            ) : (
              <Minus className="h-3 w-3" />
            )}
            {Math.abs(trend)}%
          </span>
        ) : null}
      </div>
      {hint ? <p className="mt-1 text-[11px] text-muted-foreground">{hint}</p> : null}
    </Card>
  );
}
