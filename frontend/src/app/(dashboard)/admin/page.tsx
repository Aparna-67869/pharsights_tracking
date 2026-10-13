"use client";

import * as React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Activity, BellPlus, Mail, MessageSquare, Monitor, ShieldCheck, Trash2 } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input, Select } from "@/components/ui/input";
import { Panel } from "@/components/common/panel";
import { KpiCard } from "@/components/common/kpi-card";
import { useAuth } from "@/components/providers/auth-provider";
import { fmtDateTime, fmtRelative, moduleLabel } from "@/lib/format";
import type { AlertSubscription } from "@/types/api";

const MODULES = ["ftf", "pte", "pde", "orange_book"];
const CHANNELS: Array<{ id: string; label: string; icon: React.ReactNode }> = [
  { id: "dashboard", label: "Dashboard", icon: <Monitor className="h-3 w-3" /> },
  { id: "email", label: "Email", icon: <Mail className="h-3 w-3" /> },
  { id: "teams", label: "Teams", icon: <MessageSquare className="h-3 w-3" /> },
];

/**
 * Administration: the user's own alert subscriptions plus the platform audit
 * trail. Delivery is addressed to the authenticated identity, so the panel
 * shows the exact address notifications will use.
 */
export default function AdminPage() {
  const queryClient = useQueryClient();
  const { user } = useAuth();
  const [name, setName] = React.useState("");
  const [modules, setModules] = React.useState<string[]>([]);
  const [sponsors, setSponsors] = React.useState("");
  const [drugs, setDrugs] = React.useState("");
  const [minPriority, setMinPriority] = React.useState(40);
  const [channels, setChannels] = React.useState<string[]>(["dashboard", "email", "teams"]);
  const [error, setError] = React.useState<string | null>(null);

  const subscriptions = useQuery({ queryKey: ["subscriptions"], queryFn: () => api.subscriptions() });
  const audit = useQuery({ queryKey: ["audit"], queryFn: () => api.audit(40) });

  const create = useMutation({
    mutationFn: () =>
      api.createSubscription({
        name: name || "My subscription",
        modules,
        sponsors: splitList(sponsors),
        drugs: splitList(drugs),
        min_priority: minPriority,
        channels,
      }),
    onSuccess: () => {
      setName("");
      setModules([]);
      setSponsors("");
      setDrugs("");
      setError(null);
      void queryClient.invalidateQueries({ queryKey: ["subscriptions"] });
      void queryClient.invalidateQueries({ queryKey: ["audit"] });
    },
    onError: (err: Error) =>
      setError(err instanceof ApiError ? err.message : "Could not create the subscription."),
  });

  const remove = useMutation({
    mutationFn: (id: string) => api.deleteSubscription(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["subscriptions"] }),
  });

  const toggle = (list: string[], value: string): string[] =>
    list.includes(value) ? list.filter((item) => item !== value) : [...list, value];

  return (
    <div className="space-y-4">
      <header>
        <h1 className="flex items-center gap-2 text-lg font-semibold tracking-tight">
          <ShieldCheck className="h-4.5 w-4.5 text-primary" /> Administration
        </h1>
        <p className="mt-0.5 text-xs text-muted-foreground">
          Alert subscriptions and the platform audit trail. Notifications are delivered to your authenticated
          address — no per-user mail or webhook setup required.
        </p>
      </header>

      <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <KpiCard label="My subscriptions" value={subscriptions.data?.length ?? 0} tone="primary" icon={<BellPlus className="h-3.5 w-3.5 text-primary" />} />
        <KpiCard label="Notification address" value={user?.username ?? "—"} hint="Email + Teams target" />
        <KpiCard label="Audit events" value={audit.data?.length ?? 0} hint="Most recent 40" />
        <KpiCard label="Access level" value={(user?.role ?? "viewer").replace(/_/g, " ")} tone="success" icon={<ShieldCheck className="h-3.5 w-3.5 text-success" />} />
      </section>

      <div className="grid gap-4 xl:grid-cols-12">
        <div className="space-y-4 xl:col-span-5">
          <Panel title="New alert subscription" subtitle="Choose what should reach you, and how" icon={<BellPlus className="h-3.5 w-3.5" />}>
            <div className="space-y-3">
              <div className="space-y-1.5">
                <label className="text-[11px] text-muted-foreground">Name</label>
                <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Oncology watch" className="h-9" />
              </div>

              <div className="space-y-1.5">
                <label className="text-[11px] text-muted-foreground">Modules</label>
                <div className="flex flex-wrap gap-1.5">
                  {MODULES.map((module) => (
                    <button
                      key={module}
                      onClick={() => setModules((list) => toggle(list, module))}
                      className={`rounded-full border px-2.5 py-1 text-[11px] transition-colors ${
                        modules.includes(module)
                          ? "border-primary/50 bg-primary/15 text-primary"
                          : "border-border/70 text-muted-foreground hover:bg-muted/60"
                      }`}
                    >
                      {moduleLabel(module)}
                    </button>
                  ))}
                </div>
              </div>

              <div className="grid gap-3 sm:grid-cols-2">
                <div className="space-y-1.5">
                  <label className="text-[11px] text-muted-foreground">Sponsors (comma separated)</label>
                  <Input value={sponsors} onChange={(e) => setSponsors(e.target.value)} placeholder="Pfizer, Novartis" className="h-9" />
                </div>
                <div className="space-y-1.5">
                  <label className="text-[11px] text-muted-foreground">Drugs</label>
                  <Input value={drugs} onChange={(e) => setDrugs(e.target.value)} placeholder="Lipitor, Eliquis" className="h-9" />
                </div>
              </div>

              <div className="space-y-1.5">
                <label className="text-[11px] text-muted-foreground">Minimum priority</label>
                <Select value={String(minPriority)} onChange={(e) => setMinPriority(Number(e.target.value))} className="h-9 w-40">
                  {[0, 40, 60, 70, 90].map((value) => (
                    <option key={value} value={value}>
                      {value === 0 ? "Everything" : `${value}+ (${value >= 90 ? "critical" : value >= 70 ? "high" : "medium"})`}
                    </option>
                  ))}
                </Select>
              </div>

              <div className="space-y-1.5">
                <label className="text-[11px] text-muted-foreground">Channels</label>
                <div className="flex flex-wrap gap-1.5">
                  {CHANNELS.map((channel) => (
                    <button
                      key={channel.id}
                      onClick={() => setChannels((list) => toggle(list, channel.id))}
                      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] transition-colors ${
                        channels.includes(channel.id)
                          ? "border-primary/50 bg-primary/15 text-primary"
                          : "border-border/70 text-muted-foreground hover:bg-muted/60"
                      }`}
                    >
                      {channel.icon}
                      {channel.label}
                    </button>
                  ))}
                </div>
              </div>

              {error ? <p className="text-[11px] text-destructive">{error}</p> : null}

              <Button onClick={() => create.mutate()} disabled={create.isPending} className="w-full">
                {create.isPending ? "Creating…" : "Create subscription"}
              </Button>
            </div>
          </Panel>

          <Panel title="My subscriptions" bodyClassName="p-2 space-y-2">
            {subscriptions.isLoading ? (
              <p className="p-4 text-center text-xs text-muted-foreground">Loading…</p>
            ) : (subscriptions.data?.length ?? 0) === 0 ? (
              <p className="p-6 text-center text-xs text-muted-foreground">
                No subscriptions yet. Create one to receive material changes by email and Teams.
              </p>
            ) : (
              subscriptions.data?.map((sub: AlertSubscription) => (
                <div key={sub.id} className="rounded-lg border border-border/70 p-2.5">
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <p className="text-xs font-medium">{sub.name ?? "Subscription"}</p>
                      <p className="mt-0.5 truncate text-[10px] text-muted-foreground">{sub.user_email}</p>
                    </div>
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-7 w-7 text-destructive"
                      onClick={() => remove.mutate(sub.id)}
                      aria-label="Delete subscription"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </Button>
                  </div>
                  <div className="mt-1.5 flex flex-wrap gap-1">
                    {(sub.modules.length ? sub.modules : ["all modules"]).map((module) => (
                      <Badge key={module} variant="outline" className="text-[10px]">
                        {moduleLabel(module)}
                      </Badge>
                    ))}
                    <Badge variant="secondary" className="text-[10px]">≥{sub.min_priority}</Badge>
                    {sub.channels.map((channel) => (
                      <Badge key={channel} variant="secondary" className="text-[10px]">
                        {channel}
                      </Badge>
                    ))}
                  </div>
                </div>
              ))
            )}
          </Panel>
        </div>

        <div className="xl:col-span-7">
          <Panel
            title="Audit trail"
            subtitle="Logins, searches, exports, alert actions and settings changes"
            icon={<Activity className="h-3.5 w-3.5" />}
            bodyClassName="p-0"
          >
            <div className="scrollbar-thin max-h-[640px] overflow-y-auto">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Action</th>
                    <th>Actor</th>
                    <th className="hidden md:table-cell">Resource</th>
                    <th>When</th>
                  </tr>
                </thead>
                <tbody>
                  {audit.isLoading ? (
                    <tr>
                      <td colSpan={4} className="py-8 text-center text-xs text-muted-foreground">
                        Loading audit trail…
                      </td>
                    </tr>
                  ) : (audit.data?.length ?? 0) === 0 ? (
                    <tr>
                      <td colSpan={4} className="py-8 text-center text-xs text-muted-foreground">
                        No audit events recorded yet.
                      </td>
                    </tr>
                  ) : (
                    audit.data?.map((entry) => (
                      <tr key={entry.id}>
                        <td className="font-mono text-[11px]">{entry.action}</td>
                        <td className="max-w-[180px] truncate text-[11px]">{entry.actor ?? "system"}</td>
                        <td className="hidden text-[11px] text-muted-foreground md:table-cell">
                          {entry.resource_type ?? "—"}
                          {entry.resource_id ? ` · ${entry.resource_id.slice(0, 8)}` : ""}
                        </td>
                        <td className="text-[11px] text-muted-foreground" title={fmtDateTime(entry.created_at)}>
                          {fmtRelative(entry.created_at)}
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </Panel>
        </div>
      </div>
    </div>
  );
}

function splitList(value: string): string[] {
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}
