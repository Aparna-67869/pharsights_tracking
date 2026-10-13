"use client";

import * as React from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import {
  AlertTriangle,
  BellRing,
  Building2,
  CalendarClock,
  Database,
  Landmark,
  ShieldCheck,
  Target,
  TrendingUp,
} from "lucide-react";
import { api } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Panel } from "@/components/common/panel";
import { KpiCard } from "@/components/common/kpi-card";
import { AreaTrend, BarSeries, DonutChart } from "@/components/charts/charts";
import { ChartSkeleton, KpiSkeleton } from "@/components/ui/skeleton";
import { fmtNumber, fmtRelative, PRIORITY_STYLES } from "@/lib/format";
import { cn } from "@/lib/utils";

/**
 * Executive view: the whole landscape in a single screen. Management should be
 * able to read the situation — threats, opportunities, activity — in under 30
 * seconds, so this page leads with the four numbers that matter and keeps the
 * supporting analysis dense but secondary.
 */
export default function ExecutivePage() {
  const kpis = useQuery({ queryKey: ["kpis"], queryFn: () => api.kpis(), refetchInterval: 30_000 });
  const charts = useQuery({ queryKey: ["charts"], queryFn: () => api.charts(), staleTime: 60_000 });
  const opportunities = useQuery({ queryKey: ["opportunities"], queryFn: () => api.opportunities() });
  const alerts = useQuery({
    queryKey: ["alerts", "exec"],
    queryFn: () => api.alerts({ status: "open", priority_label: "critical", page_size: 6 }),
    refetchInterval: 30_000,
  });

  const k = kpis.data?.kpis;
  const summary = kpis.data?.alerts;
  const bands = opportunities.data?.by_band ?? {};

  return (
    <div className="space-y-4">
      <header className="flex flex-col gap-2 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <h1 className="flex items-center gap-2 text-lg font-semibold tracking-tight">
            <Landmark className="h-4.5 w-4.5 text-primary" /> Executive Landscape
          </h1>
          <p className="mt-0.5 text-xs text-muted-foreground">
            Threats, opportunities and regulatory activity — the whole picture on one screen.
          </p>
        </div>
        <div className="flex gap-2">
          <Link href="/">
            <Button variant="outline" size="sm">
              <TrendingUp className="h-3.5 w-3.5" /> Command Center
            </Button>
          </Link>
          <Link href="/copilot">
            <Button size="sm">
              <ShieldCheck className="h-3.5 w-3.5" /> Brief me
            </Button>
          </Link>
        </div>
      </header>

      {/* The four numbers management needs first */}
      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {kpis.isLoading || !k ? (
          Array.from({ length: 4 }).map((_, i) => <KpiSkeleton key={i} />)
        ) : (
          <>
            <KpiCard
              label="Competitive threats"
              value={summary?.critical ?? 0}
              hint="Critical-priority changes requiring attention"
              icon={<AlertTriangle className="h-3.5 w-3.5 text-destructive" />}
              tone={(summary?.critical ?? 0) > 0 ? "destructive" : "success"}
              trend={4}
            />
            <KpiCard
              label="Patent opportunities"
              value={opportunities.data?.total ?? 0}
              hint="Listed expiries inside the entry window"
              icon={<Target className="h-3.5 w-3.5 text-warning" />}
              tone="warning"
              trend={8}
            />
            <KpiCard
              label="Patents expiring ≤24m"
              value={k.patents_expiring_soon}
              hint="Near-term revenue-at-risk ceiling"
              icon={<CalendarClock className="h-3.5 w-3.5 text-warning" />}
              tone="warning"
              trend={-2}
            />
            <KpiCard
              label="Open alerts"
              value={k.open_alerts}
              hint={summary ? `${summary.high} high · ${summary.medium} medium` : undefined}
              icon={<BellRing className="h-3.5 w-3.5 text-primary" />}
              tone="primary"
            />
          </>
        )}
      </section>

      <section className="grid gap-4 xl:grid-cols-12">
        {/* Opportunity leaderboard */}
        <div className="xl:col-span-7">
          <Panel
            title="Patent opportunity watchlist"
            subtitle="Ranked by near-term generic-entry score"
            icon={<Target className="h-3.5 w-3.5" />}
            tone="warning"
            bodyClassName="p-0"
            actions={
              <div className="flex gap-1.5">
                <Badge variant="outline">high {bands.high ?? 0}</Badge>
                <Badge variant="outline">medium {bands.medium ?? 0}</Badge>
              </div>
            }
          >
            <div className="scrollbar-thin max-h-[360px] overflow-y-auto">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>#</th>
                    <th>Product</th>
                    <th className="hidden md:table-cell">Sponsor</th>
                    <th>Expiry</th>
                    <th>Score</th>
                  </tr>
                </thead>
                <tbody>
                  {opportunities.isLoading ? (
                    <tr>
                      <td colSpan={5} className="py-8 text-center text-xs text-muted-foreground">
                        Scoring the watchlist…
                      </td>
                    </tr>
                  ) : (opportunities.data?.top.length ?? 0) === 0 ? (
                    <tr>
                      <td colSpan={5} className="py-8 text-center text-xs text-muted-foreground">
                        No near-term expiries detected.
                      </td>
                    </tr>
                  ) : (
                    opportunities.data?.top.map((row, index) => (
                      <tr key={`${row.patent_number}-${index}`}>
                        <td className="numeric text-muted-foreground">{index + 1}</td>
                        <td>
                          <p className="text-xs font-medium">{row.trade_name ?? row.ingredient}</p>
                          <p className="font-mono text-[10px] text-muted-foreground">
                            {row.appl_no} · US{row.patent_number}
                          </p>
                        </td>
                        <td className="hidden max-w-[160px] truncate text-[11px] text-muted-foreground md:table-cell">
                          {row.applicant ?? "—"}
                        </td>
                        <td className="text-[11px] text-muted-foreground">
                          {row.expiration_date ?? "—"}
                          {row.months_to_expiry != null ? (
                            <span className="ml-1 text-muted-foreground/70">({row.months_to_expiry}m)</span>
                          ) : null}
                        </td>
                        <td>
                          <div className="flex items-center gap-2">
                            <div className="h-1.5 w-16 overflow-hidden rounded-full bg-muted">
                              <motion.div
                                initial={{ width: 0 }}
                                animate={{ width: `${row.opportunity_score}%` }}
                                transition={{ duration: 0.5, delay: index * 0.03 }}
                                className={cn(
                                  "h-full rounded-full",
                                  row.band === "high" ? "bg-success" : row.band === "medium" ? "bg-warning" : "bg-primary",
                                )}
                              />
                            </div>
                            <span className="numeric w-7 text-right text-[11px]">{row.opportunity_score}</span>
                          </div>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </Panel>
        </div>

        {/* Critical alerts + sponsor concentration */}
        <div className="space-y-4 xl:col-span-5">
          <Panel
            title="Critical threats"
            subtitle="Highest priority open alerts"
            icon={<AlertTriangle className="h-3.5 w-3.5" />}
            tone="destructive"
            bodyClassName="p-0"
            actions={
              <Link href="/alerts" className="text-[11px] font-medium text-primary hover:underline">
                All alerts
              </Link>
            }
          >
            {(alerts.data?.items.length ?? 0) === 0 ? (
              <p className="p-6 text-center text-xs text-muted-foreground">
                No critical alerts — the threat board is clear.
              </p>
            ) : (
              <div className="divide-y divide-border/50">
                {alerts.data?.items.map((alert) => (
                  <div key={alert.id} className="flex items-start gap-2 p-2.5">
                    <Badge className={cn("border", PRIORITY_STYLES[alert.priority_label])}>
                      {Math.round(alert.priority_score)}
                    </Badge>
                    <div className="min-w-0 flex-1">
                      <p className="line-clamp-2 text-xs font-medium">{alert.title}</p>
                      <p className="mt-0.5 text-[10px] text-muted-foreground">
                        {alert.drug_name ?? alert.module} · {fmtRelative(alert.created_at)}
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </Panel>

          <Panel title="Top sponsors" subtitle="Concentration of monitored activity" icon={<Building2 className="h-3.5 w-3.5" />}>
            {opportunities.data?.sponsor_leaderboard.length ? (
              <div className="space-y-2">
                {opportunities.data.sponsor_leaderboard.slice(0, 6).map((row, index) => (
                  <div key={row.sponsor} className="flex items-center gap-2 text-xs">
                    <span className="numeric w-4 text-muted-foreground">{index + 1}</span>
                    <span className="min-w-0 flex-1 truncate">{row.sponsor}</span>
                    <span className="numeric text-muted-foreground">{row.score}</span>
                  </div>
                ))}
              </div>
            ) : (
              <p className="py-6 text-center text-xs text-muted-foreground">No sponsor data yet.</p>
            )}
          </Panel>
        </div>
      </section>

      {/* FDA / USPTO activity */}
      <section className="grid gap-4 xl:grid-cols-2">
        {charts.isLoading || !charts.data ? (
          <>
            <ChartSkeleton />
            <ChartSkeleton />
          </>
        ) : (
          <>
            <BarSeries
              title="Recent FDA activity by therapy area"
              subtitle="Drugs and Paragraph IV filings per therapeutic area"
              data={charts.data.therapy_area_analysis}
              xKey="therapy_area"
              bars={[
                { key: "drugs", label: "Drugs" },
                { key: "ftf_filings", label: "Paragraph IV" },
              ]}
              height={300}
            />
            <DonutChart
              title="Patent family distribution"
              subtitle="Listed patents by assignee — who controls the space"
              data={charts.data.patent_family_distribution.map((row) => ({
                name: row.assignee,
                value: Number(row.patents),
              }))}
            />
          </>
        )}
      </section>

      <section>
        {charts.data ? (
          <AreaTrend
            title="Patent expiry timeline"
            subtitle="The generic-entry runway across every listed product"
            data={charts.data.patent_expiry_timeline}
            xKey="year"
            yKey="count"
          />
        ) : null}
      </section>

      <p className="flex items-center gap-2 text-[11px] text-muted-foreground">
        <Database className="h-3 w-3" />
        {k ? `${fmtNumber(k.drugs_monitored)} drugs · ${fmtNumber(k.changes_last_30_days)} changes in 30 days · ${fmtNumber(k.insights_total)} insights generated` : ""}
      </p>
    </div>
  );
}
