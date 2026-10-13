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
  const coverage = k?.coverage;
  const byPriority = summary?.by_priority ?? {};

  return (
    <div className="space-y-4">
      {/* Hero: the executive read, plus what the platform is watching. */}
      <section className="hero hero-grid">
        <div className="relative z-10 flex flex-col gap-5 p-5 lg:flex-row lg:items-center lg:justify-between lg:p-6">
          <div className="max-w-2xl">
            <span className="status-chip border-primary/40 bg-primary/10 text-primary">
              <Landmark className="h-3 w-3" /> Executive Landscape
            </span>
            <h1 className="mt-3 text-2xl font-semibold tracking-tight lg:text-[28px]">
              Threats, opportunities &amp; regulatory activity
            </h1>
            <p className="mt-1.5 text-sm text-muted-foreground">
              The whole portfolio on one screen, scored from real FDA, USPTO and Orange Book records —
              read in under thirty seconds.
            </p>
            <div className="mt-3 flex flex-wrap gap-2">
              <span className="pill">
                <Database className="h-3 w-3" />
                {coverage ? `${fmtNumber(coverage.orange_book_products)} listed apps` : "Corpus loading"}
              </span>
              <span className="pill">
                <ShieldCheck className="h-3 w-3" />
                {coverage ? `${fmtNumber(coverage.listed_patents)} listed patents` : "—"}
              </span>
              <span className="pill">
                <Target className="h-3 w-3" />
                {coverage ? `${fmtNumber(coverage.active_moieties)} active moieties` : "—"}
              </span>
            </div>
          </div>
          <div className="flex shrink-0 gap-2 lg:border-l lg:border-border/50 lg:pl-6">
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
        </div>
      </section>

      {/* The four numbers management needs first. Each card renders its own
          skeleton until its query resolves, so a slow endpoint never shows a
          misleading "0" for a figure that is still loading. */}
      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {alerts.isLoading ? (
          <KpiSkeleton />
        ) : (
          <KpiCard
            label="Competitive threats"
            value={byPriority.critical ?? 0}
            hint="Critical-priority changes requiring attention"
            icon={<AlertTriangle className="h-3.5 w-3.5 text-destructive" />}
            tone={(byPriority.critical ?? 0) > 0 ? "destructive" : "success"}
          />
        )}
        {opportunities.isLoading ? (
          <KpiSkeleton />
        ) : (
          <KpiCard
            label="Patent opportunities"
            value={opportunities.data?.total ?? 0}
            hint="Listed expiries inside the entry window"
            icon={<Target className="h-3.5 w-3.5 text-warning" />}
            tone="warning"
          />
        )}
        {kpis.isLoading || !k ? (
          <KpiSkeleton />
        ) : (
          <KpiCard
            label="Patents expiring ≤24m"
            value={k.patents_expiring_soon}
            hint="Near-term revenue-at-risk ceiling"
            icon={<CalendarClock className="h-3.5 w-3.5 text-warning" />}
            tone="warning"
          />
        )}
        {kpis.isLoading || !k ? (
          <KpiSkeleton />
        ) : (
          <KpiCard
            label="Open alerts"
            value={k.open_alerts}
            hint={summary ? `${byPriority.high ?? 0} high · ${byPriority.medium ?? 0} medium` : undefined}
            icon={<BellRing className="h-3.5 w-3.5 text-primary" />}
            tone="primary"
          />
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
                {opportunities.isPending ? (
                  <span className="text-[11px] text-muted-foreground">scoring…</span>
                ) : (
                  <>
                    <Badge variant="outline">high {bands.high ?? 0}</Badge>
                    <Badge variant="outline">medium {bands.medium ?? 0}</Badge>
                  </>
                )}
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

          <Panel
            title="Top sponsors"
            subtitle="Aggregate generic-opportunity score by labeler"
            icon={<Building2 className="h-3.5 w-3.5" />}
          >
            {opportunities.data?.sponsor_leaderboard.length ? (
              <div className="space-y-2">
                {opportunities.data.sponsor_leaderboard.slice(0, 6).map((row, index) => (
                  <div key={row.sponsor} className="flex items-center gap-2 text-xs">
                    <span className="numeric w-4 text-muted-foreground">{index + 1}</span>
                    <span className="min-w-0 flex-1 truncate">{row.sponsor}</span>
                    <span className="numeric tabular-nums text-muted-foreground">{row.score}</span>
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
              title="Regulatory activity by month"
              subtitle="New records per module as published by the regulator"
              data={charts.data.monthly_fda_activity}
              xKey="period"
              bars={[
                { key: "ftf", label: "Paragraph IV" },
                { key: "pte", label: "PTE filings" },
                { key: "orange_book", label: "Orange Book" },
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
