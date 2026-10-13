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
import { AreaTrend, BarSeries, LineSeries } from "@/components/charts/charts";
import { ChartSkeleton, KpiSkeleton } from "@/components/ui/skeleton";
import { fmtNumber, fmtRelative, PRIORITY_STYLES } from "@/lib/format";
import { useRealtime } from "@/components/providers/realtime-provider";
import { cn } from "@/lib/utils";
import type { AlertSummary, KpiCoverage, Page, PipelineRun } from "@/types/api";

/** Labelled figure used in the corpus-coverage summary. */
function CoverageStat({
  label,
  value,
  hint,
  href,
  tone = "text-foreground",
}: {
  label: string;
  value: number;
  hint: string;
  href: string;
  tone?: string;
}) {
  return (
    <Link
      href={href}
      className="group flex flex-col gap-1 rounded-xl border border-border/70 bg-card/40 p-3 transition-colors hover:border-primary/40 hover:bg-card/70"
    >
      <span className="text-[10px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">
        {label}
      </span>
      <span className={cn("numeric text-xl font-semibold leading-none tracking-tight", tone)}>
        {fmtNumber(value)}
      </span>
      <span className="text-[11px] text-muted-foreground">{hint}</span>
    </Link>
  );
}

/**
 * Command center. Reads top to bottom: header, the monitored corpus, recent
 * change/risk KPIs, live activity, then analytics. Every figure is traceable
 * to a real published source.
 */
export default function CommandCenterPage() {
  const { connected, lastEvent } = useRealtime();
  const router = useRouter();
  const { hasScope } = useAuth();
  const canUseCopilot = hasScope("use:copilot");
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
  const coverage: KpiCoverage | undefined = k?.coverage;

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
            FDA · USPTO · Orange Book monitored continuously. Every figure below comes from a published source.
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
            <Button
              size="sm"
              disabled={!canUseCopilot}
              title={canUseCopilot ? "Ask the Copilot" : "Your role does not include copilot access"}
            >
              <Sparkles className="h-3.5 w-3.5" /> Ask the Copilot
            </Button>
          </Link>
        </div>
      </header>

      <Panel
        title="Monitored corpus"
        subtitle="Records currently held and diffed on every sweep"
        icon={<Layers className="h-3.5 w-3.5" />}
        bodyClassName="p-3"
      >
        {kpis.isLoading || !k || !coverage ? (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
            {Array.from({ length: 6 }).map((_, index) => (
              <div key={index} className="h-[74px] animate-pulse rounded-xl bg-muted/50" />
            ))}
          </div>
        ) : (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
            <CoverageStat label="FTF certifications" value={coverage.ftf_records} hint="Paragraph IV records" href="/ftf" />
            <CoverageStat label="PTE applications" value={coverage.pte_applications} hint="USPTO extensions filed" href="/pte" />
            <CoverageStat label="PTE certificates" value={coverage.pte_certificates} hint="Extensions granted" href="/pte" />
            <CoverageStat label="Active moieties" value={coverage.active_moieties} hint="Approved active moieties" href="/pde" />
            <CoverageStat label="Orange Book apps" value={coverage.orange_book_products} hint="Listed applications" href="/orange-book" />
            <CoverageStat label="Listed patents" value={coverage.listed_patents} hint="With an expiry date" href="/patents" />
          </div>
        )}
      </Panel>

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
          These counters are deltas against the last sweep — they read zero when the sources have not changed since
          the previous run, which is expected for a stable corpus.
        </p>
      </section>

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

  if (alerts.isLoading) {
    return <p className="p-4 text-center text-xs text-muted-foreground">Loading alerts…</p>;
  }
  if ((alerts.data?.items.length ?? 0) === 0) {
    return (
      <div className="flex flex-col items-center gap-1 p-8 text-center">
        <p className="text-sm font-medium text-success">Queue clear — no open alerts</p>
        <p className="text-xs text-muted-foreground">
          {summary
            ? `${summary.open} open · ${summary.critical} critical · ${summary.high} high`
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
