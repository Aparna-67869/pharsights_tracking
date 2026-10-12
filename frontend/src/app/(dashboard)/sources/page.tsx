"use client";

import * as React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Database, FileSearch, Play, RefreshCw, Server, ShieldCheck } from "lucide-react";
import { api } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { KpiCard } from "@/components/common/kpi-card";
import { fmtDateTime, fmtNumber, fmtRelative, moduleLabel } from "@/lib/format";
import type { PipelineRun, SourceDefinition } from "@/types/api";

export default function SourcesPage() {
  const queryClient = useQueryClient();
  const sources = useQuery({ queryKey: ["sources"], queryFn: () => api.sources() });
  const runs = useQuery({ queryKey: ["pipeline-runs"], queryFn: () => api.pipelineRuns(25), refetchInterval: 15_000 });

  const trigger = useMutation({
    mutationFn: () => api.triggerPipeline({}),
    onSuccess: () => {
      setTimeout(() => void queryClient.invalidateQueries({ queryKey: ["pipeline-runs"] }), 1500);
    },
  });

  const byModule = (sources.data ?? []).reduce<Record<string, number>>((acc, source) => {
    acc[source.module] = (acc[source.module] ?? 0) + 1;
    return acc;
  }, {});

  return (
    <div className="space-y-5">
      <header className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <h1 className="flex items-center gap-2 text-xl font-semibold">
            <Server className="h-5 w-5 text-primary" /> Sources &amp; Pipeline
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            The registry of monitored FDA and USPTO sources and the automation runs that collect, diff and
            analyse them.
          </p>
        </div>
        <Button onClick={() => trigger.mutate()} disabled={trigger.isPending}>
          {trigger.isPending ? <RefreshCw className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
          Run pipeline now
        </Button>
      </header>

      <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <KpiCard label="Monitored sources" value={sources.data?.length ?? 0} tone="primary" icon={<FileSearch className="h-4 w-4" />} />
        <KpiCard label="Modules covered" value={Object.keys(byModule).length} />
        <KpiCard
          label="Last run changes"
          value={runs.data?.items[0]?.changes_detected ?? 0}
          hint={runs.data?.items[0] ? fmtRelative(runs.data.items[0].started_at) : undefined}
          tone="warning"
        />
        <KpiCard
          label="Alerts raised (last run)"
          value={runs.data?.items[0]?.alerts_created ?? 0}
          tone={runs.data?.items[0]?.alerts_created ? "destructive" : "success"}
        />
      </section>

      <Tabs defaultValue="sources">
        <TabsList>
          <TabsTrigger value="sources">
            <Database className="h-3.5 w-3.5" /> Source registry
          </TabsTrigger>
          <TabsTrigger value="runs">
            <RefreshCw className="h-3.5 w-3.5" /> Pipeline runs
          </TabsTrigger>
        </TabsList>

        <TabsContent value="sources" className="mt-4">
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {(sources.data ?? []).map((source: SourceDefinition) => (
              <Card key={source.id} className="p-4">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium">{source.name}</p>
                    <p className="font-mono text-[10px] text-muted-foreground">{source.code}</p>
                  </div>
                  <Badge variant="outline">{moduleLabel(source.module)}</Badge>
                </div>
                {source.description ? (
                  <p className="mt-2 line-clamp-2 text-xs text-muted-foreground">{source.description}</p>
                ) : null}
                <div className="mt-3 space-y-1 text-[11px]">
                  <div className="flex items-center justify-between">
                    <span className="text-muted-foreground">Cadence</span>
                    <span>{source.cadence ?? "scheduled"}</span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-muted-foreground">Document</span>
                    <span>{source.document_kind ?? "—"}</span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-muted-foreground">Last checked</span>
                    <span>{source.last_checked_at ? fmtRelative(source.last_checked_at) : "never"}</span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-muted-foreground">Status</span>
                    {source.last_error ? (
                      <Badge variant="destructive">error</Badge>
                    ) : source.last_checked_at ? (
                      <Badge variant="success">healthy</Badge>
                    ) : (
                      <Badge variant="outline">not yet run</Badge>
                    )}
                  </div>
                </div>
                <a
                  href={source.url}
                  target="_blank"
                  rel="noreferrer noopener"
                  className="mt-3 block truncate text-[10px] text-primary hover:underline"
                >
                  {source.url}
                </a>
              </Card>
            ))}
          </div>
        </TabsContent>

        <TabsContent value="runs" className="mt-4">
          <Card className="overflow-hidden">
            <CardHeader>
              <CardTitle>Pipeline run history</CardTitle>
              <p className="mt-0.5 text-xs text-muted-foreground">
                Each run collects every source, diffs against the last snapshot, scores the deltas and dispatches
                alerts.
              </p>
            </CardHeader>
            <CardContent className="p-0">
              <div className="scrollbar-thin max-h-[58vh] overflow-auto">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Status</th>
                      <th>Trigger</th>
                      <th>Started</th>
                      <th className="text-right">Sources</th>
                      <th className="text-right">Changes</th>
                      <th className="text-right">Insights</th>
                      <th className="text-right">Alerts</th>
                      <th className="text-right">Duration</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(runs.data?.items ?? []).map((run: PipelineRun) => (
                      <tr key={run.id}>
                        <td>
                          <Badge
                            variant={
                              run.status === "completed"
                                ? "success"
                                : run.status === "failed"
                                  ? "destructive"
                                  : "secondary"
                            }
                          >
                            {run.status}
                          </Badge>
                        </td>
                        <td className="text-xs">{run.trigger}</td>
                        <td className="text-xs">
                          <p className="tabular-nums">{fmtDateTime(run.started_at)}</p>
                          <p className="text-[10px] text-muted-foreground">{fmtRelative(run.started_at)}</p>
                        </td>
                        <td className="text-right tabular-nums text-xs">
                          {fmtNumber(run.sources_checked ?? 0)}
                          {run.sources_changed ? (
                            <span className="ml-1 text-[10px] text-warning-foreground dark:text-amber-300">
                              ({run.sources_changed} changed)
                            </span>
                          ) : null}
                        </td>
                        <td className="text-right tabular-nums text-xs">{fmtNumber(run.changes_detected ?? 0)}</td>
                        <td className="text-right tabular-nums text-xs">{fmtNumber(run.insights_generated ?? 0)}</td>
                        <td className="text-right tabular-nums text-xs">
                          {run.alerts_created ? (
                            <span className="font-medium text-destructive">{run.alerts_created}</span>
                          ) : (
                            "0"
                          )}
                        </td>
                        <td className="text-right tabular-nums text-xs">
                          {run.duration_ms ? `${(run.duration_ms / 1000).toFixed(1)}s` : "—"}
                        </td>
                      </tr>
                    ))}
                    {(runs.data?.items ?? []).length === 0 ? (
                      <tr>
                        <td colSpan={8} className="py-8 text-center text-xs text-muted-foreground">
                          No pipeline runs recorded yet.
                        </td>
                      </tr>
                    ) : null}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      <Card>
        <CardContent className="flex flex-wrap items-center gap-4 pt-4 text-xs text-muted-foreground">
          <span className="flex items-center gap-1.5">
            <ShieldCheck className="h-3.5 w-3.5 text-primary" /> Every collection and change is written to an
            immutable audit log.
          </span>
          <span className="flex items-center gap-1.5">
            <Database className="h-3.5 w-3.5 text-primary" /> Archived artifacts are retained for offline access
            and version comparison.
          </span>
        </CardContent>
      </Card>
    </div>
  );
}
