"use client";

import * as React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BellRing, Check, CheckCheck, Mail, MessageSquare, Send, X } from "lucide-react";
import { api } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Select } from "@/components/ui/input";
import { EmptyState, TableSkeleton } from "@/components/ui/skeleton";
import { DonutChart } from "@/components/charts/charts";
import { KpiCard } from "@/components/common/kpi-card";
import { fmtDateTime, fmtRelative, PRIORITY_STYLES, moduleLabel } from "@/lib/format";
import { cn } from "@/lib/utils";
import { useRealtime } from "@/components/providers/realtime-provider";
import type { Alert } from "@/types/api";

const CHANNEL_ICONS: Record<string, React.ReactNode> = {
  email: <Mail className="h-3 w-3" />,
  teams: <MessageSquare className="h-3 w-3" />,
  slack: <MessageSquare className="h-3 w-3" />,
  dashboard: <BellRing className="h-3 w-3" />,
};

export default function AlertsPage() {
  const queryClient = useQueryClient();
  const { subscribe } = useRealtime();
  const [page, setPage] = React.useState(1);
  const [status, setStatus] = React.useState("open");
  const [priority, setPriority] = React.useState("");
  const [module, setModule] = React.useState("");

  React.useEffect(() => setPage(1), [status, priority, module]);

  const params = {
    page,
    page_size: 25,
    status,
    priority_label: priority || undefined,
    module: module || undefined,
  };

  const alerts = useQuery({ queryKey: ["alerts", params], queryFn: () => api.alerts(params) });
  const summary = useQuery({ queryKey: ["alert-summary"], queryFn: () => api.alertSummary() });

  const mutation = useMutation({
    mutationFn: ({ id, next }: { id: string; next: string }) => api.updateAlert(id, { status: next }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["alerts"] });
      void queryClient.invalidateQueries({ queryKey: ["alert-summary"] });
      void queryClient.invalidateQueries({ queryKey: ["kpis"] });
    },
  });

  React.useEffect(
    () =>
      subscribe((event) => {
        if (event.topic.startsWith("alert") || event.event_type?.includes("alert")) {
          void alerts.refetch();
          void summary.refetch();
        }
      }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [],
  );

  const s = summary.data;

  return (
    <div className="space-y-5">
      <header>
        <h1 className="flex items-center gap-2 text-xl font-semibold">
          <BellRing className="h-5 w-5 text-primary" /> Alert Management
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Priority-scored notifications. The engine suppresses routine deltas so only material regulatory
          events reach this queue.
        </p>
      </header>

      <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
        {s ? (
          <>
            <KpiCard label="Open" value={s.open} tone={s.open > 0 ? "destructive" : "success"} icon={<BellRing className="h-4 w-4" />} />
            <KpiCard label="Critical" value={s.critical} tone="destructive" />
            <KpiCard label="High" value={s.high} tone="warning" />
            <KpiCard label="Medium" value={s.medium} tone="primary" />
            <KpiCard label="Low" value={s.low} />
          </>
        ) : null}
      </section>

      <div className="grid gap-4 xl:grid-cols-4">
        <div className="xl:col-span-3 space-y-3">
          <div className="flex flex-wrap items-center gap-2">
            <Select value={status} onChange={(event) => setStatus(event.target.value)} className="h-8 w-44 text-xs">
              <option value="open">Open</option>
              <option value="acknowledged">Acknowledged</option>
              <option value="resolved">Resolved</option>
              <option value="dismissed">Dismissed</option>
              <option value="all">All statuses</option>
            </Select>
            <Select value={priority} onChange={(event) => setPriority(event.target.value)} className="h-8 w-40 text-xs">
              {["", "critical", "high", "medium", "low"].map((option) => (
                <option key={option} value={option}>
                  {option ? option[0].toUpperCase() + option.slice(1) : "All priorities"}
                </option>
              ))}
            </Select>
            <Select value={module} onChange={(event) => setModule(event.target.value)} className="h-8 w-44 text-xs">
              {["", "ftf", "pte", "pde", "orange_book"].map((option) => (
                <option key={option} value={option}>
                  {option ? moduleLabel(option) : "All modules"}
                </option>
              ))}
            </Select>
            <span className="ml-auto text-xs text-muted-foreground">{alerts.data?.total ?? 0} alerts</span>
          </div>

          {alerts.isLoading ? (
            <TableSkeleton rows={6} cols={2} />
          ) : (alerts.data?.items.length ?? 0) === 0 ? (
            <EmptyState
              icon={<BellRing className="h-8 w-8" />}
              title="No alerts in this view"
              description="Either nothing material has changed, or the alerts matching your filters have been handled."
            />
          ) : (
            <>
              {alerts.data?.items.map((alert: Alert) => (
                <Card key={alert.id} className="p-4">
                  <div className="flex flex-wrap items-start gap-3">
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <Badge className={cn("border", PRIORITY_STYLES[alert.priority_label])}>
                          {alert.priority_label.toUpperCase()} {Math.round(alert.priority_score)}
                        </Badge>
                        <Badge variant="outline">{moduleLabel(alert.module)}</Badge>
                        <Badge variant="secondary">{alert.event_type}</Badge>
                        <Badge variant={alert.status === "open" ? "warning" : "success"}>{alert.status}</Badge>
                        <span className="text-[11px] text-muted-foreground">{fmtRelative(alert.created_at)}</span>
                      </div>
                      <p className="mt-1.5 text-sm font-medium">{alert.title}</p>
                      {alert.message ? (
                        <p className="mt-0.5 text-xs text-muted-foreground">{alert.message}</p>
                      ) : null}
                      <div className="mt-2 flex flex-wrap items-center gap-3 text-[11px] text-muted-foreground">
                        {alert.drug_name ? <span>Drug: {alert.drug_name}</span> : null}
                        {alert.sponsor_name ? <span>Sponsor: {alert.sponsor_name}</span> : null}
                        <span>{fmtDateTime(alert.created_at)}</span>
                        {alert.acknowledged_by ? <span>Acknowledged by {alert.acknowledged_by}</span> : null}
                        {(alert.channels_sent ?? []).length ? (
                          <span className="flex items-center gap-1">
                            Delivered:
                            {(alert.channels_sent ?? []).map((channel) => (
                              <span key={channel} className="inline-flex items-center gap-0.5 rounded border border-border px-1">
                                {CHANNEL_ICONS[channel] ?? <Send className="h-3 w-3" />}
                                {channel}
                              </span>
                            ))}
                          </span>
                        ) : null}
                      </div>
                    </div>
                    <div className="flex shrink-0 gap-1.5">
                      {alert.status === "open" ? (
                        <Button
                          variant="outline"
                          size="sm"
                          disabled={mutation.isPending}
                          onClick={() => mutation.mutate({ id: alert.id, next: "acknowledged" })}
                        >
                          <Check className="h-3.5 w-3.5" /> Acknowledge
                        </Button>
                      ) : null}
                      {alert.status !== "resolved" && alert.status !== "dismissed" ? (
                        <Button
                          variant="outline"
                          size="sm"
                          disabled={mutation.isPending}
                          onClick={() => mutation.mutate({ id: alert.id, next: "resolved" })}
                        >
                          <CheckCheck className="h-3.5 w-3.5" /> Resolve
                        </Button>
                      ) : null}
                      {alert.status === "open" ? (
                        <Button
                          variant="ghost"
                          size="sm"
                          disabled={mutation.isPending}
                          onClick={() => mutation.mutate({ id: alert.id, next: "dismissed" })}
                        >
                          <X className="h-3.5 w-3.5" /> Dismiss
                        </Button>
                      ) : null}
                    </div>
                  </div>
                </Card>
              ))}
              <div className="flex items-center justify-between pt-1 text-xs text-muted-foreground">
                <span>
                  Page {alerts.data?.page} of {alerts.data?.pages}
                </span>
                <div className="flex gap-2">
                  <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage((v) => v - 1)}>
                    Prev
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={page >= (alerts.data?.pages ?? 1)}
                    onClick={() => setPage((v) => v + 1)}
                  >
                    Next
                  </Button>
                </div>
              </div>
            </>
          )}
        </div>

        <div className="space-y-4">
          {s ? (
            <DonutChart
              title="Alerts by priority"
              subtitle="All-time distribution"
              data={[
                { name: "Critical", value: s.critical },
                { name: "High", value: s.high },
                { name: "Medium", value: s.medium },
                { name: "Low", value: s.low },
              ].filter((entry) => entry.value > 0)}
              height={220}
            />
          ) : null}
          <Card>
            <CardHeader>
              <CardTitle>Notification channels</CardTitle>
              <p className="mt-0.5 text-xs text-muted-foreground">Where dispatched alerts are delivered</p>
            </CardHeader>
            <CardContent className="space-y-2 text-xs">
              {[
                { name: "Dashboard", detail: "Real-time WebSocket push" },
                { name: "Email", detail: "SMTP relay / Graph API" },
                { name: "Microsoft Teams", detail: "Incoming webhook" },
                { name: "Slack", detail: "Bot token / webhook" },
              ].map((channel) => (
                <div key={channel.name} className="flex items-center gap-2 rounded-lg border border-border/70 bg-surface/40 px-3 py-2">
                  <span className="grid h-6 w-6 place-items-center rounded bg-muted/60">
                    {CHANNEL_ICONS[channel.name.toLowerCase().split(" ")[0]] ?? <Send className="h-3 w-3" />}
                  </span>
                  <div>
                    <p className="font-medium">{channel.name}</p>
                    <p className="text-[10px] text-muted-foreground">{channel.detail}</p>
                  </div>
                </div>
              ))}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
