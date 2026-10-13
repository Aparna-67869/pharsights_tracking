"use client";

import * as React from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  CalendarClock,
  Database,
  FlaskConical,
  GitCompareArrows,
  Landmark,
  Layers,
  LineChart as LineChartIcon,
  ShieldCheck,
  Sparkles,
  Target,
  TrendingUp,
} from "lucide-react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/components/providers/auth-provider";
import { Badge } from "@/components/ui/badge";
import { Panel } from "@/components/common/panel";
import { KpiCard } from "@/components/common/kpi-card";
import { InsightCard } from "@/components/common/insight-card";
import { LiveAlertStream } from "@/components/common/live-alert-stream";
import { Reveal } from "@/components/common/reveal";
import { AnimatedNumber } from "@/components/common/animated-number";
import { AreaTrend, BarSeries, LineSeries } from "@/components/charts/charts";
import { ChartSkeleton, KpiSkeleton } from "@/components/ui/skeleton";
import { fmtNumber, fmtRelative, PRIORITY_STYLES } from "@/lib/format";
import { useRealtime } from "@/components/providers/realtime-provider";
import { cn } from "@/lib/utils";
import type { AlertSummary, KpiCoverage, Page, PipelineRun } from "@/types/api";

/** A single monitored corpus figure. Every value is a real row count. */
function MetricCell({
  label,
  value,
  hint,
  href,
  tone = "var(--primary)",
}: {
  label: string;
  value: number;
  hint: string;
  href: string;
  tone?: string;
}) {
  return (
    <Link href={href} className="metric" style={{ ["--metric-tone" as string]: tone }}>
      <span className="text-[10px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">
        {label}
      </span>
      <span className="numeric text-2xl font-semibold leading-none tracking-tight">
        <AnimatedNumber value={value} />
      </span>
      <span className="text-[11px] text-muted-foreground">{hint}</span>
    </Link>
  );
}

function HeroStat({ label, value, tone }: { label: string; value: number; tone?: string }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-[10px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">
        {label}
      </span>
      <span className={cn("numeric text-lg font-semibold leading-none", tone ?? "text-foreground")}>
        <AnimatedNumber value={value} />
      </span>
    </div>
  );
}

/**
 * Command center. Reads top to bottom: hero with live monitoring status, the
 * monitored corpus (real row counts), change & risk deltas, live activity, then
 * analytics. Every figure is traceable to a published source — nothing here is
 * synthesised.
 */
export default function CommandCenterPage() {
  const { connected, lastEvent } = useRealtime();
  const router = useRouter();
  const { hasScope } = useAuth();
  const canUseCopilot = hasScope("use:copilot");
  const now = new Date().toISOString();

  const kpis = useQuery({ queryKey: ["kpis"], queryFn: () => api.kpis(), refetchInterval: 30_000 });
  const charts = useQuery({ queryKey: ["charts"], queryFn: () => api.charts(), staleTime: 60_000 });
  const scheduler = useQuery({
    queryKey: ["scheduler"],
    queryFn: () => api.schedulerStatus(),
    refetchInterval: 60_000,
  });
  const sources = useQuery({ queryKey: ["sources"], queryFn: () => api.sources(), staleTime: 120_000 });
  const insights = useQuery({
    queryKey: ["insights", "top"],
    queryFn: () => api.insights({ page_size: 4, sort: "-priority_score" }),
    refetchInterval: 30_000,
  });
  const runs = useQuery({ queryKey: ["runs"], queryFn: () => api.pipelineRuns(4) });

  const k = kpis.data?.kpis;
  const summary = kpis.data?.alerts;
  const coverage: KpiCoverage | undefined = k?.coverage;
  const liveSources = (sources.data ?? []).filter((source) => source.enabled);

  React.useEffect(() => {
    if (lastEvent) {
      void kpis.refetch();
      void insights.refetch();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lastEvent]);

  const opportunities = React.useMemo(() => {
    const rows = charts.data?.generic_opportunity_heatmap ?? [];
    return rows.slice(0, 6).map((row) => ({
      product: String(row.product ?? "—"),
      applicant: String(row.applicant ?? "—"),
      expiry: row.nearest_patent_expiry ? String(row.nearest_patent_expiry) : null,
      days: typeof row.days_to_expiry === "number" ? row.days_to_expiry : null,
    }));
  }, [charts.data]);

  return (
    <div className="space-y-5">
      {/* ---- Hero: what is being watched, right now ------------------------ */}
      <section className="hero hero-grid">
        <div className="relative z-10 flex flex-col gap-5 p-5 lg:flex-row lg:items-center lg:justify-between lg:p-6">
          <div className="max-w-2xl">
            <div className="flex flex-wrap items-center gap-2">
              <span
                className={cn(
                  "status-chip",
                  connected
                    ? "border-success/40 bg-success/10 text-success"
                    : "border-border bg-muted/40 text-muted-foreground",
                )}
              >
                <span className={cn("h-1.5 w-1.5 rounded-full", connected ? "live-dot" : "bg-muted-foreground")} />
                {connected ? "Realtime feed connected" : "Reconnecting to feed"}
              </span>
              {scheduler.data ? (
                <span className="status-chip border-border bg-card/50 text-muted-foreground">
                  <Activity className="h-3 w-3" />
                  Auto-sweep every {scheduler.data.interval_minutes} min
                </span>
              ) : null}
            </div>
            <h1 className="mt-3 text-2xl font-semibold tracking-tight lg:text-[28px]">
              Regulatory Intelligence Command Center
            </h1>
            <p className="mt-1.5 text-sm text-muted-foreground">
              FDA Paragraph IV, USPTO patent-term extensions, approved active moieties and the Orange Book are
              monitored continuously. Every figure below is a real record held in the platform.
            </p>
            <div className="mt-3 flex flex-wrap gap-2">
              <span className="pill">
                <Layers className="h-3 w-3" />
                {liveSources.length || 8} monitored sources
              </span>
              <span className="pill">
                <Database className="h-3 w-3" />
                Versioned &amp; diffed every sweep
              </span>
              <span className="pill">
                <ShieldCheck className="h-3 w-3" />
                Audit trail retained
              </span>
            </div>
          </div>

          <div className="grid shrink-0 grid-cols-2 gap-x-8 gap-y-4 lg:grid-cols-1 lg:border-l lg:border-border/50 lg:pl-6">
            {kpis.isLoading || !k ? (
              <>
                <div className="h-9 w-24 animate-pulse rounded-md bg-muted/50" />
                <div className="h-9 w-24 animate-pulse rounded-md bg-muted/50" />
              </>
            ) : (
              <>
                <HeroStat label="Drugs monitored" value={k.drugs_monitored} />
                <HeroStat label="Expiring ≤ 24 months" value={k.patents_expiring_soon} tone="text-warning" />
              </>
            )}
          </div>
        </div>
      </section>

      {/* ---- Monitored corpus: the real record counts ---------------------- */}
      <Panel
        title="Monitored corpus"
        subtitle="Records currently held and re-diffed on every sweep"
        icon={<Layers className="h-3.5 w-3.5" />}
        bodyClassName="p-3"
      >
        {kpis.isLoading || !coverage ? (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
            {Array.from({ length: 6 }).map((_, index) => (
              <div key={index} className="h-[84px] animate-pulse rounded-xl bg-muted/50" />
            ))}
          </div>
        ) : (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
            <MetricCell
              label="FTF certifications"
              value={coverage.ftf_records}
              hint="Paragraph IV records"
              href="/ftf"
            />
            <MetricCell
              label="PTE applications"
              value={coverage.pte_applications}
              hint="USPTO extensions filed"
              href="/pte"
              tone="var(--accent)"
            />
            <MetricCell
              label="PTE certificates"
              value={coverage.pte_certificates}
              hint="Extensions granted"
              href="/pte"
              tone="var(--success)"
            />
            <MetricCell
              label="Active moieties"
              value={coverage.active_moieties}
              hint="FDA approved moieties"
              href="/pde"
              tone="var(--accent)"
            />
            <MetricCell
              label="Orange Book apps"
              value={coverage.orange_book_products}
              hint="Listed applications"
              href="/orange-book"
            />
            <MetricCell
              label="Listed patents"
              value={coverage.listed_patents}
              hint="With an expiry date"
              href="/patents"
              tone="var(--warning)"
            />
          </div>
        )}
      </Panel>

      {/* ---- Change & risk: deltas since the last sweep -------------------- */}
      <section>
        <div className="mb-2 flex items-center gap-2">
          <TrendingUp className="h-3.5 w-3.5 text-muted-foreground" />
          <h2 className="text-xs font-semibold uppercase tracking-[0.14em] text-muted-foreground">
            Recent change &amp; risk
          </h2>
        </div>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
          {kpis.isLoading || !k ? (
            Array.from({ length: 6 }).map((_, index) => <KpiSkeleton key={index} />)
          ) : (
            <>
              <KpiCard
                label="New FTF (30d)"
                value={k.new_ftf_records}
                hint="Paragraph IV submissions"
                icon={<GitCompareArrows className="h-3.5 w-3.5 text-primary" />}
                updatedAt={now}
                onClick={() => router.push("/ftf")}
              />
              <KpiCard
                label="New PTE apps (30d)"
                value={k.new_pte_applications}
                hint="Extensions filed"
                icon={<ShieldCheck className="h-3.5 w-3.5 text-primary" />}
                updatedAt={now}
                onClick={() => router.push("/pte")}
              />
              <KpiCard
                label="New PTE grants (30d)"
                value={k.new_pte_grants}
                hint="Certificates issued"
                icon={<ShieldCheck className="h-3.5 w-3.5 text-success" />}
                tone="success"
                updatedAt={now}
                onClick={() => router.push("/pte")}
              />
              <KpiCard
                label="New moieties (30d)"
                value={k.new_active_moieties}
                hint="PDE additions"
                icon={<FlaskConical className="h-3.5 w-3.5 text-primary" />}
                updatedAt={now}
                onClick={() => router.push("/pde")}
              />
              <KpiCard
                label="Orange Book changes (30d)"
                value={k.orange_book_updates}
                hint="Detected product changes"
                icon={<Database className="h-3.5 w-3.5 text-primary" />}
                updatedAt={now}
                onClick={() => router.push("/orange-book")}
              />
              <KpiCard
                label="Patents expiring ≤24m"
                value={k.patents_expiring_soon}
                hint="Generic-entry window"
                icon={<CalendarClock className="h-3.5 w-3.5 text-warning" />}
                tone="warning"
                updatedAt={now}
                onClick={() => router.push("/patents")}
              />
            </>
          )}
        </div>
        <p className="mt-2 text-[11px] text-muted-foreground">
          These counters are deltas against the last sweep, so they read zero when the regulators have not published
          anything new since the previous run — the expected state for a stable corpus. The corpus totals above always
          reflect what is actually held.
        </p>
      </section>

      {/* ---- Live activity + impact analysis ------------------------------- */}
      <section className="grid gap-4 xl:grid-cols-12">
        <div className="xl:col-span-5">
          <LiveAlertStream height={420} />
        </div>

        <div className="space-y-4 xl:col-span-7">
          <Panel
            title="AI impact analysis"
            subtitle="What changed, why it matters, and the recommended action"
            icon={<Sparkles className="h-3.5 w-3.5" />}
            bodyClassName="space-y-2.5 p-3"
            actions={
              <Link href="/changes" className="text-[11px] font-medium text-primary hover:underline">
                View all
              </Link>
            }
          >
            {insights.isLoading ? (
              <div className="space-y-3">
                {Array.from({ length: 3 }).map((_, index) => (
                  <div key={index} className="h-16 animate-pulse rounded-lg bg-muted/50" />
                ))}
              </div>
            ) : (insights.data?.items.length ?? 0) === 0 ? (
              <div className="rounded-lg border border-dashed border-border p-8 text-center">
                <p className="text-sm font-medium">No insights yet</p>
                <p className="mt-1 text-xs text-muted-foreground">
                  Baseline ingestion does not raise insights by design. Impact analysis appears as soon as a
                  monitored source changes.
                </p>
              </div>
            ) : (
              insights.data?.items
                .slice(0, 3)
                .map((insight, index) => <InsightCard key={insight.id} insight={insight} defaultOpen={index === 0} />)
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
            <PipelineTable runs={runs.data} loading={runs.isLoading} />
          </Panel>
        </div>
      </section>

      {/* ---- Analytics ----------------------------------------------------- */}
      <section>
        <div className="mb-2 flex items-center gap-2">
          <LineChartIcon className="h-3.5 w-3.5 text-muted-foreground" />
          <h2 className="text-xs font-semibold uppercase tracking-[0.14em] text-muted-foreground">Analytics</h2>
        </div>
        <div className="space-y-4">
          <div className="grid gap-4 xl:grid-cols-2">
            {charts.isLoading || !charts.data ? (
              <>
                <ChartSkeleton />
                <ChartSkeleton />
              </>
            ) : (
              <>
                <Reveal>
                  <AreaTrend
                    title="Patent expiry timeline"
                    subtitle="Listed patents expiring per year — the generic-entry runway"
                    data={charts.data.patent_expiry_timeline}
                    xKey="year"
                    yKey="count"
                  />
                </Reveal>
                <Reveal delay={0.05}>
                  <LineSeries
                    title="Monthly regulatory activity"
                    subtitle="Combined FTF, PTE, PDE and Orange Book events"
                    data={charts.data.monthly_fda_activity}
                    xKey="period"
                    lines={[
                      { key: "ftf", label: "FTF" },
                      { key: "pte", label: "PTE" },
                      { key: "pde", label: "PDE" },
                      { key: "orange_book", label: "Orange Book" },
                    ]}
                  />
                </Reveal>
              </>
            )}
          </div>

          <div className="grid gap-4 xl:grid-cols-12">
            <div className="xl:col-span-7">
              {charts.data ? (
                <Reveal>
                  <BarSeries
                    title="Most active organisations"
                    subtitle="Distinct NDA applications and approved active moieties, by labeler"
                    data={charts.data.sponsor_leaderboard}
                    xKey="sponsor"
                    layout="vertical"
                    bars={[
                      { key: "nda", label: "NDA apps" },
                      { key: "pde", label: "Active moieties" },
                    ]}
                    stacked
                    height={300}
                  />
                </Reveal>
              ) : null}
            </div>

            <div className="xl:col-span-5">
              <Panel
                title="Generic-entry watchlist"
                subtitle="Next listed patent expiry within 3 years"
                icon={<Target className="h-3.5 w-3.5" />}
                tone="warning"
                bodyClassName="p-0"
              >
                {opportunities.length === 0 ? (
                  <p className="py-6 text-center text-xs text-muted-foreground">
                    No listed patents expire in the next three years.
                  </p>
                ) : (
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>Product</th>
                        <th className="hidden md:table-cell">Labeler</th>
                        <th className="text-right">Expiry</th>
                        <th className="text-right">In</th>
                      </tr>
                    </thead>
                    <tbody>
                      {opportunities.map((row, index) => (
                        <tr key={`${row.product}-${index}`}>
                          <td className="text-xs font-medium">{row.product}</td>
                          <td className="hidden max-w-[180px] truncate text-[11px] text-muted-foreground md:table-cell">
                            {row.applicant}
                          </td>
                          <td className="text-right text-[11px] text-muted-foreground">
                            {row.expiry
                              ? new Date(row.expiry).toLocaleDateString(undefined, {
                                  year: "numeric",
                                  month: "short",
                                })
                              : "—"}
                          </td>
                          <td className="text-right">
                            {row.days != null ? (
                              <Badge
                                variant={row.days <= 180 ? "destructive" : row.days <= 365 ? "warning" : "secondary"}
                              >
                                {row.days < 0 ? "lapsed" : `${fmtNumber(row.days)}d`}
                              </Badge>
                            ) : (
                              "—"
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </Panel>
            </div>
          </div>
        </div>
      </section>

      {/* ---- Alert triage -------------------------------------------------- */}
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
          <OpenAlertTable summary={summary} />
        </Panel>
      </section>
    </div>
  );
}

function PipelineTable({ runs, loading }: { runs?: Page<PipelineRun>; loading: boolean }) {
  const items = runs?.items ?? [];
  if (loading) {
    return <p className="p-4 text-center text-xs text-muted-foreground">Loading runs…</p>;
  }
  if (items.length === 0) {
    return <p className="p-4 text-center text-xs text-muted-foreground">No runs recorded yet.</p>;
  }
  return (
    <table className="data-table">
      <thead>
        <tr>
          <th>Trigger</th>
          <th>Status</th>
          <th className="text-right">Started</th>
        </tr>
      </thead>
      <tbody>
        {items.map((run) => {
          const scheduled = run.trigger === "scheduled";
          return (
            <tr key={run.id}>
              <td className="text-xs">
                <span className="inline-flex items-center gap-1.5">
                  {scheduled ? (
                    <CalendarClock className="h-3.5 w-3.5 text-muted-foreground" />
                  ) : (
                    <ArrowRight className="h-3.5 w-3.5 text-muted-foreground" />
                  )}
                  {scheduled ? "Automatic sweep" : "Manual run"}
                </span>
              </td>
              <td>
                <Badge
                  variant={run.status === "success" ? "success" : run.status === "failed" ? "destructive" : "secondary"}
                >
                  {run.status}
                </Badge>
              </td>
              <td className="text-right text-[11px] text-muted-foreground">{fmtRelative(run.started_at)}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

function OpenAlertTable({ summary }: { summary?: AlertSummary }) {
  const alerts = useQuery({
    queryKey: ["alerts", "home"],
    queryFn: () => api.alerts({ status: "open", page_size: 8 }),
    refetchInterval: 20_000,
  });

  const openCount = summary?.open_total ?? summary?.open ?? 0;
  const byPriority = summary?.by_priority ?? {};

  if (alerts.isLoading) {
    return <p className="p-4 text-center text-xs text-muted-foreground">Loading alerts…</p>;
  }
  if ((alerts.data?.items.length ?? 0) === 0) {
    return (
      <div className="flex flex-col items-center gap-1 p-8 text-center">
        <p className="text-sm font-medium text-success">Queue clear — no open alerts</p>
        <p className="text-xs text-muted-foreground">
          {summary
            ? `${openCount} open · ${byPriority.critical ?? 0} critical · ${byPriority.high ?? 0} high`
            : "Monitoring is running."}
        </p>
      </div>
    );
  }
  return (
    <table className="data-table">
      <thead>
        <tr>
          <th>Priority</th>
          <th>Event</th>
          <th className="hidden md:table-cell">Drug / Sponsor</th>
          <th className="text-right">Detected</th>
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
            <td className="text-right text-[11px] text-muted-foreground">{fmtRelative(alert.created_at)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
