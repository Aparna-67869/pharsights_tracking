"use client";

import * as React from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import {
  Activity,
  AlertTriangle,
  BellRing,
  Brain,
  CalendarClock,
  Database,
  FileText,
  FlaskConical,
  GitCompareArrows,
  Layers,
  Sparkles,
  TrendingUp,
} from "lucide-react";
import { api } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ChartSkeleton, KpiSkeleton, TableSkeleton } from "@/components/ui/skeleton";
import { KpiCard } from "@/components/common/kpi-card";
import { InsightCard } from "@/components/common/insight-card";
import { AreaTrend, BarSeries, DonutChart, Heatmap, LineSeries } from "@/components/charts/charts";
import { fmtCompact, fmtNumber, fmtRelative, PRIORITY_STYLES } from "@/lib/format";
import { useRealtime } from "@/components/providers/realtime-provider";
import { cn } from "@/lib/utils";

export default function CommandCenterPage() {
  const { connected, lastEvent } = useRealtime();

  const kpis = useQuery({ queryKey: ["kpis"], queryFn: () => api.kpis(), refetchInterval: 30_000 });
  const charts = useQuery({ queryKey: ["charts"], queryFn: () => api.charts(), staleTime: 60_000 });
  const insights = useQuery({
    queryKey: ["insights", "top"],
    queryFn: () => api.insights({ page_size: 6, sort: "-priority_score" }),
    refetchInterval: 30_000,
  });
  const alerts = useQuery({
    queryKey: ["alerts", "open"],
    queryFn: () => api.alerts({ status: "open", page_size: 6 }),
    refetchInterval: 20_000,
  });
  const runs = useQuery({ queryKey: ["runs"], queryFn: () => api.pipelineRuns(3) });

  const k = kpis.data?.kpis;
  const summary = kpis.data?.alerts;

  React.useEffect(() => {
    if (lastEvent) {
      void kpis.refetch();
      void alerts.refetch();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lastEvent]);

  const heat = charts.data?.generic_opportunity_heatmap ?? [];
  const heatRows = Array.from(new Set(heat.map((cell) => String(cell.applicant ?? "—")))).slice(0, 12);
  const heatCols = Array.from(new Set(heat.map((cell) => String(cell.ingredient ?? "—")))).slice(0, 14);

  return (
    <div className="space-y-5">
      <header className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-xl font-semibold">Regulatory Intelligence Command Center</h1>
            <Badge variant={connected ? "success" : "secondary"}>
              <span className={cn("h-1.5 w-1.5 rounded-full", connected ? "bg-success" : "bg-muted-foreground")} />
              {connected ? "Live" : "Reconnecting"}
            </Badge>
          </div>
          <p className="mt-1 text-sm text-muted-foreground">
            Continuous monitoring of FDA and USPTO sources — every change detected, scored and explained.
            {lastEvent ? (
              <span className="ml-1 text-primary">Updated {fmtRelative(new Date().toISOString())}</span>
            ) : null}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button variant="outline" size="sm" onClick={() => void kpis.refetch()}>
            <Activity className="h-3.5 w-3.5" /> Refresh
          </Button>
          <Link href="/copilot">
            <Button size="sm">
              <Sparkles className="h-3.5 w-3.5" /> Ask the Copilot
            </Button>
          </Link>
        </div>
      </header>

      {/* KPI grid */}
      <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
        {kpis.isLoading || !k ? (
          Array.from({ length: 10 }).map((_, index) => <KpiSkeleton key={index} />)
        ) : (
          <>
            <KpiCard
              label="Drugs monitored"
              value={k.drugs_monitored}
              hint="Distinct products across all sources"
              icon={<Layers className="h-4 w-4" />}
              tone="primary"
            />
            <KpiCard
              label="Patents expiring ≤24m"
              value={k.patents_expiring_soon}
              hint="Near-term generic-entry window"
              icon={<CalendarClock className="h-4 w-4" />}
              tone="warning"
            />
            <KpiCard
              label="New FTF records"
              value={k.new_ftf_records}
              hint="Paragraph IV filings (30 days)"
              icon={<GitCompareArrows className="h-4 w-4" />}
            />
            <KpiCard
              label="New PTE applications"
              value={k.new_pte_applications}
              hint="USPTO extensions filed (30 days)"
              icon={<FileText className="h-4 w-4" />}
            />
            <KpiCard
              label="New PTE grants"
              value={k.new_pte_grants}
              hint="Certificates issued (30 days)"
              icon={<FileText className="h-4 w-4" />}
              tone="success"
            />
            <KpiCard
              label="New active moieties"
              value={k.new_active_moieties}
              hint="PDE additions (30 days)"
              icon={<FlaskConical className="h-4 w-4" />}
            />
            <KpiCard
              label="Orange Book updates"
              value={k.orange_book_updates}
              hint="Product records changed (30 days)"
              icon={<Database className="h-4 w-4" />}
            />
            <KpiCard
              label="Open alerts"
              value={k.open_alerts}
              hint={summary ? `${summary.critical} critical · ${summary.high} high` : undefined}
              icon={<BellRing className="h-4 w-4" />}
              tone={k.open_alerts > 0 ? "destructive" : "default"}
            />
            <KpiCard
              label="High-risk opportunities"
              value={k.high_risk_opportunities}
              hint="Critical/High priority insights"
              icon={<AlertTriangle className="h-4 w-4" />}
              tone="warning"
            />
            <KpiCard
              label="Changes (30 days)"
              value={k.changes_last_30_days}
              hint={`${fmtCompact(k.insights_total)} insights generated all-time`}
              icon={<TrendingUp className="h-4 w-4" />}
            />
          </>
        )}
      </section>

      {/* Priority insight + open alerts */}
      <section className="grid gap-4 xl:grid-cols-3">
        <Card className="xl:col-span-2">
          <CardHeader className="flex-row items-center justify-between">
            <div>
              <CardTitle className="flex items-center gap-2">
                <Brain className="h-4 w-4 text-primary" /> Priority intelligence
              </CardTitle>
              <p className="mt-0.5 text-xs text-muted-foreground">
                AI impact analyses, ranked by business priority score
              </p>
            </div>
            <Link href="/changes">
              <Button variant="ghost" size="sm">
                View all
              </Button>
            </Link>
          </CardHeader>
          <CardContent className="space-y-2">
            {insights.isLoading ? (
              <div className="space-y-2">
                {Array.from({ length: 3 }).map((_, index) => (
                  <div key={index} className="h-16 animate-pulse rounded-lg bg-muted/50" />
                ))}
              </div>
            ) : (insights.data?.items.length ?? 0) === 0 ? (
              <div className="rounded-lg border border-dashed border-border p-8 text-center">
                <p className="text-sm font-medium">No insights yet</p>
                <p className="mt-1 text-xs text-muted-foreground">
                  The platform runs continuously in the background. Insights appear here as soon as a
                  monitored source changes — baseline ingestion does not raise alerts by design.
                </p>
              </div>
            ) : (
              insights.data?.items.map((insight, index) => (
                <InsightCard key={insight.id} insight={insight} defaultOpen={index === 0} />
              ))
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex-row items-center justify-between">
            <div>
              <CardTitle className="flex items-center gap-2">
                <BellRing className="h-4 w-4 text-destructive" /> Open alerts
              </CardTitle>
              <p className="mt-0.5 text-xs text-muted-foreground">Only material changes reach users</p>
            </div>
            <Link href="/alerts">
              <Button variant="ghost" size="sm">
                Manage
              </Button>
            </Link>
          </CardHeader>
          <CardContent className="space-y-2">
            {alerts.isLoading ? (
              <div className="space-y-2">
                {Array.from({ length: 3 }).map((_, index) => (
                  <div key={index} className="h-14 animate-pulse rounded-lg bg-muted/50" />
                ))}
              </div>
            ) : (alerts.data?.items.length ?? 0) === 0 ? (
              <div className="rounded-lg border border-dashed border-border p-8 text-center">
                <p className="text-sm font-medium">All clear</p>
                <p className="mt-1 text-xs text-muted-foreground">
                  No open alerts. The alert engine suppresses routine deltas below the configured
                  priority threshold.
                </p>
              </div>
            ) : (
              alerts.data?.items.map((alert) => (
                <div
                  key={alert.id}
                  className="rounded-lg border border-border/70 bg-surface/50 p-3 transition-colors hover:bg-muted/40"
                >
                  <div className="flex items-center justify-between gap-2">
                    <Badge className={cn("border", PRIORITY_STYLES[alert.priority_label])}>
                      {alert.priority_label.toUpperCase()} {Math.round(alert.priority_score)}
                    </Badge>
                    <span className="text-[11px] text-muted-foreground">
                      {fmtRelative(alert.created_at)}
                    </span>
                  </div>
                  <p className="mt-1.5 line-clamp-2 text-sm font-medium">{alert.title}</p>
                  <p className="mt-0.5 text-[11px] text-muted-foreground">{alert.event_type}</p>
                </div>
              ))
            )}
          </CardContent>
        </Card>
      </section>

      {/* Charts */}
      <section className="grid gap-4 xl:grid-cols-2">
        {charts.isLoading || !charts.data ? (
          <>
            <ChartSkeleton />
            <ChartSkeleton />
          </>
        ) : (
          <>
            <AreaTrend
              title="Patent expiry timeline"
              subtitle="Listed patents expiring per year — the generic-entry runway"
              data={charts.data.patent_expiry_timeline}
              xKey="year"
              yKey="count"
            />
            <LineSeries
              title="Monthly FDA activity"
              subtitle="Combined FTF, PTE, PDE and Orange Book events (24 months)"
              data={charts.data.monthly_fda_activity}
              xKey="period"
              lines={[
                { key: "ftf", label: "FTF" },
                { key: "pte", label: "PTE" },
                { key: "pde", label: "PDE" },
                { key: "orange_book", label: "Orange Book" },
              ]}
            />
            <BarSeries
              title="Sponsor leaderboard"
              subtitle="Top sponsors by monitored activity across every module"
              data={charts.data.sponsor_leaderboard}
              xKey="sponsor"
              layout="vertical"
              bars={[
                { key: "nda", label: "NDA" },
                { key: "pde", label: "PDE" },
                { key: "pte", label: "PTE" },
              ]}
              stacked
              height={320}
            />
            <BarSeries
              title="Therapy area analysis"
              subtitle="Drugs and Paragraph IV filings by therapy area"
              data={charts.data.therapy_area_analysis}
              xKey="therapy_area"
              bars={[
                { key: "drugs", label: "Drugs" },
                { key: "ftf_filings", label: "Paragraph IV" },
              ]}
              height={320}
            />
            <DonutChart
              title="Patent family distribution"
              subtitle="Listed patents by assignee"
              data={charts.data.patent_family_distribution.map((row) => ({
                name: row.assignee,
                value: Number(row.patents),
              }))}
            />
            <Card>
              <CardHeader>
                <CardTitle>Generic opportunity heatmap</CardTitle>
                <p className="mt-0.5 text-xs text-muted-foreground">
                  Products with listed patents expiring within 3 years, by sponsor and ingredient
                </p>
              </CardHeader>
              <CardContent>
                {heat.length === 0 ? (
                  <p className="py-10 text-center text-xs text-muted-foreground">
                    No near-term expiries detected.
                  </p>
                ) : (
                  <Heatmap
                    title=""
                    cells={heat.map((cell) => ({
                      row: String(cell.applicant ?? "—"),
                      col: String(cell.ingredient ?? "—"),
                      value: Number(cell.opportunity_score ?? 0),
                    }))}
                    rowLabels={heatRows}
                    colLabels={heatCols}
                    getValue={(row, col) => {
                      const match = heat.find(
                        (cell) => String(cell.applicant ?? "—") === row && String(cell.ingredient ?? "—") === col,
                      );
                      return match ? Number(match.opportunity_score ?? 0) : 0;
                    }}
                  />
                )}
              </CardContent>
            </Card>
          </>
        )}
      </section>

      {/* Pipeline health */}
      <section>
        {runs.isLoading ? (
          <TableSkeleton rows={3} cols={5} />
        ) : (
          <Card>
            <CardHeader className="flex-row items-center justify-between">
              <div>
                <CardTitle>Automation pipeline</CardTitle>
                <p className="mt-0.5 text-xs text-muted-foreground">
                  Background SOP runs — collect, diff, analyse, alert
                </p>
              </div>
              <Link href="/sources">
                <Button variant="ghost" size="sm">
                  Sources
                </Button>
              </Link>
            </CardHeader>
            <CardContent className="space-y-2">
              {(runs.data?.items ?? []).map((run) => (
                <div
                  key={run.id}
                  className="flex flex-wrap items-center gap-3 rounded-lg border border-border/70 bg-surface/40 px-3 py-2 text-xs"
                >
                  <Badge variant={run.status === "completed" ? "success" : run.status === "failed" ? "destructive" : "secondary"}>
                    {run.status}
                  </Badge>
                  <span className="text-muted-foreground">{run.trigger}</span>
                  <span className="ml-auto tabular-nums text-muted-foreground">
                    {fmtNumber(run.changes_detected ?? 0)} changes · {fmtNumber(run.insights_generated ?? 0)} insights ·{" "}
                    {fmtNumber(run.alerts_created ?? 0)} alerts
                  </span>
                  <span className="text-muted-foreground">{fmtRelative(run.started_at)}</span>
                </div>
              ))}
            </CardContent>
          </Card>
        )}
      </section>
    </div>
  );
}
