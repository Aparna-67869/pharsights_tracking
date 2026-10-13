"use client";

import * as React from "react";
import { ArrowDownRight, ArrowUpRight, Minus } from "lucide-react";
import { motion } from "framer-motion";
import { AnimatedNumber } from "@/components/common/animated-number";
import { Sparkline } from "@/components/common/sparkline";
import { cn } from "@/lib/utils";
import { fmtRelative } from "@/lib/format";

type Tone = "default" | "primary" | "success" | "warning" | "destructive";

const TONE: Record<Tone, { hsl: string; text: string; chip: string }> = {
  default: { hsl: "var(--muted-foreground)", text: "text-muted-foreground", chip: "bg-muted/60" },
  primary: { hsl: "var(--primary)", text: "text-primary", chip: "bg-primary/12" },
  success: { hsl: "var(--success)", text: "text-success", chip: "bg-success/12" },
  warning: { hsl: "var(--warning)", text: "text-warning", chip: "bg-warning/12" },
  destructive: { hsl: "var(--destructive)", text: "text-destructive", chip: "bg-destructive/12" },
};

/**
 * Premium KPI tile: value, growth vs. previous period, mini trend, freshness and
 * a drill-down affordance. The whole tile is a button when `onClick` is given.
 */
export function KpiCard({
  label,
  value,
  hint,
  icon: Icon,
  tone = "default",
  trend,
  series,
  updatedAt,
  onClick,
  sparkHeight = 30,
  className,
}: {
  label: string;
  value: number | string;
  hint?: string;
  icon?: React.ReactNode;
  tone?: Tone;
  trend?: number | null;
  series?: number[];
  updatedAt?: string | number | Date;
  onClick?: () => void;
  sparkHeight?: number;
  className?: string;
}) {
  const t = TONE[tone];
  const points = series && series.length >= 2 ? series : null;

  const inner = (
    <>
      <div className="flex items-start justify-between gap-2">
        <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">
          {label}
        </p>
        {Icon ? (
          <span className={cn("grid h-7 w-7 place-items-center rounded-lg", t.chip)}>{Icon}</span>
        ) : null}
      </div>

      <div className="mt-2 flex items-end justify-between gap-2">
        <div className="flex items-end gap-1.5">
          <span className={cn("numeric text-[26px] font-semibold leading-none tracking-tight", t.text)}>
            {typeof value === "number" ? <AnimatedNumber value={value} /> : value}
          </span>
          {typeof trend === "number" ? (
            <span
              className={cn(
                "mb-0.5 inline-flex items-center gap-0.5 text-[11px] font-medium",
                trend > 0 ? "text-success" : trend < 0 ? "text-destructive" : "text-muted-foreground",
              )}
              title="Change vs. previous period"
            >
              {trend > 0 ? (
                <ArrowUpRight className="h-3 w-3" />
              ) : trend < 0 ? (
                <ArrowDownRight className="h-3 w-3" />
              ) : (
                <Minus className="h-3 w-3" />
              )}
              {trend > 0 ? "+" : ""}
              {trend}%
            </span>
          ) : null}
        </div>
        {points ? <Sparkline data={points} height={sparkHeight} tone={`hsl(${t.hsl})`} /> : null}
      </div>

      <div className="mt-2 flex items-center justify-between gap-2">
        {hint ? <p className="truncate text-[11px] text-muted-foreground">{hint}</p> : <span />}
        {updatedAt ? (
          <span className="shrink-0 text-[10px] text-muted-foreground/70">
            {fmtRelative(typeof updatedAt === "string" ? updatedAt : new Date(updatedAt).toISOString())}
          </span>
        ) : null}
      </div>

      {onClick ? (
        <span className="pointer-events-none absolute bottom-2 right-2.5 text-[10px] font-medium text-primary opacity-0 transition-opacity group-hover:opacity-100">
          Details {"\u2192"}
        </span>
      ) : null}
    </>
  );

  const className2 = cn(
    "panel kpi-topline group relative overflow-hidden px-3.5 py-3 text-left",
    onClick && "cursor-pointer hover:ring-1 hover:ring-primary/40",
    className,
  );
  const style = { ["--kpi-tone" as string]: `hsl(${t.hsl})` };

  if (onClick) {
    return (
      <motion.button
        onClick={onClick}
        whileHover={{ y: -2 }}
        transition={{ type: "spring", stiffness: 320, damping: 26 }}
        className={className2}
        style={style}
      >
        {inner}
      </motion.button>
    );
  }
  return (
    <div className={className2} style={style}>
      {inner}
    </div>
  );
}
