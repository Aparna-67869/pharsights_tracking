"use client";

import * as React from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import {
  Activity,
  AlertTriangle,
  BellRing,
  Brain,
  CalendarClock,
  Database,
  FlaskConical,
  GitCompareArrows,
  Landmark,
  Layers,
  ShieldCheck,
  Sparkles,
  Target,
  TrendingUp,
} from "lucide-react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Panel } from "@/components/common/panel";
import { KpiCard } from "@/components/common/kpi-card";
import { InsightCard } from "@/components/common/insight-card";
import { LiveAlertStream } from "@/components/common/live-alert-stream";
import { AreaTrend, BarSeries, LineSeries } from "@/components/charts/charts";
import { ChartSkeleton, KpiSkeleton } from "@/components/ui/skeleton";
import { fmtCompact, fmtNumber, fmtRelative, PRIORITY_STYLES } from "@/lib/format";
import { useRealtime } from "@/components/providers/realtime-provider";
import { cn } from "@/lib/utils";

/**
 * Home: the executive command center. Layout follows the intelligence-desk
 * mental model — KPI wall, live event stream, market/FDA/USPTO activity, then
 * AI-narrated insight and opportunity sections.
 */
export default function CommandCenterPage() {
  const { connected, lastEvent } = useRealtime();
  const router = useRouter();
  const now = new Date().toISOString();

  const kpis = useQuery({ queryKey: ["kpis"], queryFn: () => api.kpis(), refetchInterval: 30_000 });
  const charts = useQuery({ queryKey: ["charts"], queryFn: () => api.charts(), staleTime: 60_000 });
  const insights = useQuery({
    queryKey: ["insights", "top"],
    queryFn: () => api.insights({ page_size: 4, sort: "-priority_score" }),
    refetchInterval: 30_000,
  });
  const runs = useQuery({ queryKey: ["runs"], queryFn: () => api.pipelineRuns(4) });

  const k = kpis.data?.kpis;
  const summary = kpis.data?.alerts;

  React.useEffect(() => {
    if (lastEvent) {
      void kpis.refetch();
      void insights.refetch();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lastEvent]);

  const opportunities = React.useMemo(() => {
    const rows = charts.data?.generic_opportunity_heatmap ?? [];
    const bySponsor = new Map<string, number>();
    for (const row of rows) {
      const sponsor = String(row.applicant ?? "—");
      bySponsor.set(sponsor, (bySponsor.get(sponsor) ?? 0) + Number(row.opportunity_score ?? 0));
    }
    return Array.from(bySponsor.entries())
      .map(([sponsor, score]) => ({ sponsor, score }))
      .sort((a, b) => b.score - a.score)
      .slice(0, 6);
  }, [charts.data]);

  return (
    <div className="space-y-4">
      {/* Header */}
      <header className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-lg font-semibold tracking-tight">Regulatory Intelligence Command Center</h1>
            <Badge variant={connected ? "success" : "secondary"} className="gap-1">
              <span className={cn("h-1.5 w-1.5 rounded-full", connected ? "bg-success" : "bg-muted-foreground")} />
              {connected ? "Live" : "Reconnecting"}
            </Badge>
          </div>
          <p className="mt-0.5 text-xs text-muted-foreground">
            FDA · USPTO · Orange Book monitored continuously — every change detected, scored and explained.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button variant="outline" size="sm" onClick={() => void kpis.refetch()}>
            <Activity className="h-3.5 w-3.5" /> Refresh
          </Button>
          <Link href="/executive">
            <Button variant="outline" size="sm">
              <TrendingUp className="h-3.5 w-3.5" /> Executive view
            </Button>
          </Link>
          <Link href="/copilot">
            <Button size="sm">
              <Sparkles className="h-3.5 w-3.5" /> Ask the Copilot
            </Button>
          </Link>
        </div>
      </header>

      {/* KPI wall */}
      <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
        {kpis.isLoading || !k ? (
          Array.from({ length: 10 }).map((_, index) => <KpiSkeleton key={index} />)
        ) : (
          <>
            <KpiCard
              label="Drugs monitored"
              value={k.drugs_monitored}
              hint="Distinct products across all sources"
              icon={<Layers className="h-3.5 w-3.5 text-primary" />}
              tone="primary"
              trend={6}
              updatedAt={now}
              onClick={() => router.push("/search")}
            />
            <KpiCard
              label="Patents expiring ≤24m"
              value={k.patents_expiring_soon}
              hint="Near-term generic-entry window"
              icon={<CalendarClock className="h-3.5 w-3.5 text-warning" />}
              tone="warning"
              trend={-3}
              updatedAt={now}
            />
            <KpiCard
              label="New FTF records"
              value={k.new_ftf_records}
              hint="Paragraph IV filings (30 days)"
              icon={<GitCompareArrows className="h-3.5 w-3.5 text-primary" />}
              tone="primary"
              trend={12}
              updatedAt={now}
            />
            <KpiCard
              label="New PTE applications"
              value={k.new_pte_applications}
              hint="USPTO extensions filed (30 days)"
              icon={<ShieldCheck className="h-3.5 w-3.5 text-primary" />}
              trend={4}
              updatedAt={now}
            />
            <KpiCard
              label="New PTE grants"
              value={k.new_pte_grants}
              hint="Certificates issued (30 days)"
              icon={<ShieldCheck className="h-3.5 w-3.5 text-success" />}
              tone="success"
              trend={9}
              updatedAt={now}
            />
            <KpiCard
              label="New active moieties"
              value={k.new_active_moieties}
              hint="PDE additions (30 days)"
              icon={<FlaskConical className="h-3.5 w-3.5 text-primary" />}
              trend={2}
              updatedAt={now}
            />
            <KpiCard
              label="Orange Book changes"
              value={k.orange_book_updates}
              hint="Product records changed (30 days)"
              icon={<Database className="h-3.5 w-3.5 text-primary" />}
              trend={-1}
              updatedAt={now}
            />
            <KpiCard
              label="Critical alerts"
              value={summary?.critical ?? 0}
              hint={summary ? `${summary.open} open · ${summary.high} high` : undefined}
              icon={<BellRing className="h-3.5 w-3.5 text-destructive" />}
              tone={(summary?.critical ?? 0) > 0 ? "destructive" : "success"}
              updatedAt={now}
              onClick={() => router.push("/alerts")}
            />
            <KpiCard
              label="Generic opportunities"
              value={k.high_risk_opportunities}
              hint="Critical/High priority insights"
              icon={<Target className="h-3.5 w-3.5 text-warning" />}
              tone="warning"
              trend={7}
              updatedAt={now}
            />
            <KpiCard
              label="Changes (30 days)"
              value={k.changes_last_30_days}
              hint={`${fmtCompact(k.insights_total)} insights generated all-time`}
              icon={<TrendingUp className="h-3.5 w-3.5 text-primary" />}
              trend={5}
              updatedAt={now}
            />
          </>
        )}
      </section>

      {/* Live stream + AI insight */}
      <section className="grid gap-4 xl:grid-cols-12">
        <div className="xl:col-span-5 2xl:col-span-4">
          <LiveAlertStream height={430} />
        </div>

        <div className="space-y-4 xl:col-span-7 2xl:col-span-8">
          <Panel
            title="AI impact analysis"
            subtitle="What changed, why it matters, and the recommended action"
            icon={<Brain className="h-3.5 w-3.5" />}
            tone="primary"
            bodyClassName="p-2.5 space-y-2"
            actions={
              <Link href="/changes" className="text-[11px] font-medium text-primary hover:underline">
                View all
              </Link>
            }
          >
            {insights.isLoading ? (
              <div className="space-y-2">
                {Array.from({ length: 3 }).map((_, index) => (
                  <div key={index} className="h-16 animate-pulse rounded-lg bg-muted/50" />
                ))}
              </div>
            ) : (insights.data?.items.length ?? 0) === 0 ? (
              <div className="m-1 rounded-lg border border-dashed border-border p-8 text-center">
                <p className="text-sm font-medium">No insights yet</p>
                <p className="mt-1 text-xs text-muted-foreground">
                  Baseline ingestion does not raise insights by design. Impact analysis appears as soon as a
                  monitored source changes.
                </p>
              </div>
            ) : (
              insights.data?.items.map((insight, index) => (
                <InsightCard key={insight.id} insight={insight} defaultOpen={index === 0} />
              ))
            )}
          </Panel>
        </div>
      </section>

      {/* Market intelligence activity */}
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
          </>
        )}
      </section>

      {/* USPTO + opportunities + pipeline */}
      <section className="grid gap-4 xl:grid-cols-12">
        <div className="xl:col-span-7">
          {charts.data ? (
            <BarSeries
              title="Sponsor leaderboard"
              subtitle="Most active sponsors across every monitored module"
              data={charts.data.sponsor_leaderboard}
              xKey="sponsor"
              layout="vertical"
              bars={[
                { key: "nda", label: "NDA" },
                { key: "pde", label: "PDE" },
                { key: "pte", label: "PTE" },
              ]}
              stacked
              height={300}
            />
          ) : null}
        </div>

        <div className="space-y-4 xl:col-span-5">
          <Panel
            title="Competitive opportunities"
            subtitle="Sponsors ranked by near-term generic-entry score"
            icon={<Target className="h-3.5 w-3.5" />}
            tone="warning"
            bodyClassName="p-3 space-y-2.5"
          >
            {opportunities.length === 0 ? (
              <p className="py-6 text-center text-xs text-muted-foreground">No near-term expiries detected.</p>
            ) : (
              opportunities.map((row, index) => (
                <div key={row.sponsor} className="flex items-center gap-3">
                  <span className="numeric w-5 text-xs text-muted-foreground">{index + 1}</span>
                  <span className="min-w-0 flex-1 truncate text-xs font-medium">{row.sponsor}</span>
                  <div className="h-1.5 w-24 overflow-hidden rounded-full bg-muted">
                    <motion.div
                      initial={{ width: 0 }}
                      animate={{ width: `${Math.min(100, (row.score / (opportunities[0]?.score || 1)) * 100)}%` }}
                      transition={{ duration: 0.6, delay: index * 0.05 }}
                      className="h-full rounded-full bg-warning"
                    />
                  </div>
                  <span className="numeric w-8 text-right text-xs">{Math.round(row.score)}</span>
                </div>
              ))
            )}
          </Panel>

          <Panel
            title="Automation pipeline"
            subtitle="Background SOP runs — collect, diff, analyse, alert"
            icon={<Landmark className="h-3.5 w-3.5" />}
            bodyClassName="p-0"
            actions={
              <Link href="/sources" className="text-[11px] font-medium text-primary hover:underline">
                Open
              </Link>
            }
          >
            {(runs.data?.items.length ?? 0) === 0 ? (
              <p className="p-4 text-center text-xs text-muted-foreground">No runs recorded yet.</p>
            ) : (
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Run</th>
                    <th>Status</th>
                    <th>Started</th>
                  </tr>
                </thead>
                <tbody>
                  {runs.data?.items.map((run) => (
                    <tr key={run.id}>
                      <td className="font-mono text-[11px]">{run.trigger}</td>
                      <td>
                        <Badge
                          variant={
                            run.status === "success" ? "success" : run.status === "failed" ? "destructive" : "secondary"
                          }
                        >
                          {run.status}
                        </Badge>
                      </td>
                      <td className="text-[11px] text-muted-foreground">{fmtRelative(run.started_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </Panel>
        </div>
      </section>

      {/* Alert triage strip */}
      <section>
        <Panel
          title="Open alert triage"
          subtitle="Only material changes reach this queue"
          icon={<AlertTriangle className="h-3.5 w-3.5" />}
          tone="destructive"
          bodyClassName="p-0"
          actions={
            <Link href="/alerts" className="text-[11px] font-medium text-primary hover:underline">
              Manage alerts
            </Link>
          }
        >
          <OpenAlertTable />
        </Panel>
      </section>
    </div>
  );
}

function OpenAlertTable() {
  const alerts = useQuery({
    queryKey: ["alerts", "home"],
    queryFn: () => api.alerts({ status: "open", page_size: 8 }),
    refetchInterval: 20_000,
  });

  if (alerts.isLoading) {
    return <p className="p-4 text-center text-xs text-muted-foreground">Loading alerts…</p>;
  }
  if ((alerts.data?.items.length ?? 0) === 0) {
    return <p className="p-6 text-center text-xs text-muted-foreground">No open alerts — the queue is clear.</p>;
  }
  return (
    <table className="data-table">
      <thead>
        <tr>
          <th>Priority</th>
          <th>Event</th>
          <th className="hidden md:table-cell">Drug / Sponsor</th>
          <th>Detected</th>
        </tr>
      </thead>
      <tbody>
        {alerts.data?.items.map((alert) => (
          <tr key={alert.id}>
            <td>
              <Badge className={cn("border", PRIORITY_STYLES[alert.priority_label])}>
                {alert.priority_label.toUpperCase()} {Math.round(alert.priority_score)}
              </Badge>
            </td>
            <td>
              <p className="text-xs font-medium">{alert.title}</p>
              <p className="font-mono text-[10px] text-muted-foreground">{alert.event_type}</p>
            </td>
            <td className="hidden text-[11px] text-muted-foreground md:table-cell">
              {alert.drug_name ?? "—"} {alert.sponsor_name ? `· ${alert.sponsor_name}` : ""}
            </td>
            <td className="text-[11px] text-muted-foreground">{fmtRelative(alert.created_at)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
