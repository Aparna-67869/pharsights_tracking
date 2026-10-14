"use client";

import * as React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Activity,
  BellPlus,
  Database,
  Mail,
  MessageSquare,
  Monitor,
  ShieldCheck,
  Trash2,
  UserPlus,
  Users,
} from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input, Select } from "@/components/ui/input";
import { Panel } from "@/components/common/panel";
import { KpiCard } from "@/components/common/kpi-card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useAuth } from "@/components/providers/auth-provider";
import { fmtDateTime, fmtRelative, moduleLabel } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { AlertSubscription, SourceDefinition } from "@/types/api";

const MODULES = ["ftf", "pte", "pde", "orange_book"];
const ROLES = ["admin", "analyst", "regulatory_affairs", "ip_counsel", "executive", "viewer"];
const CHANNEL_META: Record<string, { label: string; icon: React.ReactNode }> = {
  dashboard: { label: "Dashboard", icon: <Monitor className="h-3 w-3" /> },
  email: { label: "Email", icon: <Mail className="h-3 w-3" /> },
  teams: { label: "Teams", icon: <MessageSquare className="h-3 w-3" /> },
  slack: { label: "Slack", icon: <MessageSquare className="h-3 w-3" /> },
};

/**
 * Administration: alert subscriptions, account management (administrators),
 * the live source registry and the platform audit trail.
 *
 * Everything added here is written to the database and read back through the
 * API, so a created subscription, account or role change is immediately
 * visible in the tables on this page.
 */
export default function AdminPage() {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";

  return (
    <div className="space-y-4">
      <header>
        <h1 className="flex items-center gap-2 text-lg font-semibold tracking-tight">
          <ShieldCheck className="h-4.5 w-4.5 text-primary" /> Administration
        </h1>
        <p className="mt-0.5 text-xs text-muted-foreground">
          Manage alert subscriptions, platform accounts, the monitored source registry and the audit
          trail. Subscriptions are scoped to your authenticated identity.
        </p>
      </header>

      <div className="grid gap-4 xl:grid-cols-12">
        <div className="space-y-4 xl:col-span-5">
          <SubscriptionPanel />
        </div>
        <div className="xl:col-span-7">
          <AdminTabs isAdmin={isAdmin} />
        </div>
      </div>
    </div>
  );
}

function AdminTabs({ isAdmin }: { isAdmin: boolean }) {
  return (
    <Tabs defaultValue={isAdmin ? "users" : "registry"}>
      <TabsList>
        {isAdmin ? (
          <TabsTrigger value="users">
            <Users className="h-3.5 w-3.5" /> Accounts
          </TabsTrigger>
        ) : null}
        <TabsTrigger value="registry">
          <Database className="h-3.5 w-3.5" /> Source registry
        </TabsTrigger>
        <TabsTrigger value="audit">
          <Activity className="h-3.5 w-3.5" /> Audit trail
        </TabsTrigger>
      </TabsList>
      {isAdmin ? (
        <TabsContent value="users" className="mt-4">
          <AccountsPanel />
        </TabsContent>
      ) : null}
      <TabsContent value="registry" className="mt-4">
        <RegistryPanel />
      </TabsContent>
      <TabsContent value="audit" className="mt-4">
        <AuditPanel />
      </TabsContent>
    </Tabs>
  );
}

/** Accounts: list, create, change role, activate/deactivate (admins only). */
function AccountsPanel() {
  const queryClient = useQueryClient();
  const users = useQuery({ queryKey: ["users"], queryFn: () => api.users() });
  const [fullName, setFullName] = React.useState("");
  const [email, setEmail] = React.useState("");
  const [password, setPassword] = React.useState("");
  const [error, setError] = React.useState<string | null>(null);

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ["users"] });
    void queryClient.invalidateQueries({ queryKey: ["audit"] });
  };

  const create = useMutation({
    mutationFn: () => api.provisionUser({ full_name: fullName, email, password }),
    onSuccess: () => {
      setFullName("");
      setEmail("");
      setPassword("");
      setError(null);
      invalidate();
    },
    onError: (err: Error) =>
      setError(err instanceof ApiError ? err.message : "Could not create the account."),
  });

  const update = useMutation({
    mutationFn: ({ id, body }: { id: string; body: { role?: string; is_active?: boolean } }) =>
      api.updateUser(id, body),
    onSuccess: invalidate,
  });

  return (
    <div className="space-y-4">
      <Panel
        title="Add account"
        subtitle="Provisioned accounts can sign in immediately"
        icon={<UserPlus className="h-3.5 w-3.5" />}
      >
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="space-y-1.5">
            <label className="text-[11px] text-muted-foreground">Full name</label>
            <Input value={fullName} onChange={(e) => setFullName(e.target.value)} placeholder="Jane Analyst" className="h-9" />
          </div>
          <div className="space-y-1.5">
            <label className="text-[11px] text-muted-foreground">Email</label>
            <Input value={email} onChange={(e) => setEmail(e.target.value)} placeholder="jane@company.com" className="h-9" />
          </div>
          <div className="space-y-1.5">
            <label className="text-[11px] text-muted-foreground">Temporary password</label>
            <Input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="At least 8 characters"
              className="h-9"
            />
          </div>
          <div className="flex items-end">
            <Button
              className="h-9 w-full"
              disabled={create.isPending || !fullName || !email || password.length < 8}
              onClick={() => create.mutate()}
            >
              {create.isPending ? "Creating…" : "Create account"}
            </Button>
          </div>
        </div>
        {error ? <p className="mt-2 text-[11px] text-destructive">{error}</p> : null}
        <p className="mt-2 text-[10px] text-muted-foreground">
          New accounts start with the viewer role. Promote them in the table below.
        </p>
      </Panel>

      <Panel title="Platform accounts" subtitle="Role and access control" bodyClassName="p-0" icon={<Users className="h-3.5 w-3.5" />}>
        <div className="scrollbar-thin max-h-[520px] overflow-auto">
          <table className="data-table">
            <thead>
              <tr>
                <th>Account</th>
                <th>Role</th>
                <th>Status</th>
                <th className="hidden md:table-cell">Last login</th>
              </tr>
            </thead>
            <tbody>
              {users.isLoading ? (
                <tr>
                  <td colSpan={4} className="py-8 text-center text-xs text-muted-foreground">
                    Loading accounts…
                  </td>
                </tr>
              ) : (
                users.data?.map((account) => (
                  <tr key={account.id}>
                    <td>
                      <p className="text-xs font-medium">{account.full_name}</p>
                      <p className="truncate text-[10px] text-muted-foreground">{account.email}</p>
                    </td>
                    <td>
                      <Select
                        value={account.role}
                        className="h-8 w-40 text-[11px]"
                        onChange={(event) => update.mutate({ id: account.id, body: { role: event.target.value } })}
                      >
                        {ROLES.map((role) => (
                          <option key={role} value={role}>
                            {role.replace(/_/g, " ")}
                          </option>
                        ))}
                      </Select>
                    </td>
                    <td>
                      <button
                        onClick={() => update.mutate({ id: account.id, body: { is_active: !account.is_active } })}
                        className="cursor-pointer"
                        title={account.is_active ? "Deactivate" : "Activate"}
                      >
                        <Badge variant={account.is_active ? "success" : "secondary"} className="text-[10px]">
                          {account.is_active ? "active" : "disabled"}
                        </Badge>
                      </button>
                    </td>
                    <td className="hidden text-[11px] text-muted-foreground md:table-cell">
                      {account.last_login_at ? fmtRelative(account.last_login_at) : "never"}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </Panel>
    </div>
  );
}

/** Source registry: what the platform monitors, with real last-run state. */
function RegistryPanel() {
  const sources = useQuery({ queryKey: ["sources"], queryFn: () => api.sources() });
  return (
    <Panel
      title="Monitored sources"
      subtitle="Every collector the platform runs automatically"
      icon={<Database className="h-3.5 w-3.5" />}
      bodyClassName="p-0"
    >
      <div className="scrollbar-thin max-h-[640px] overflow-auto">
        <table className="data-table">
          <thead>
            <tr>
              <th>Source</th>
              <th>Module</th>
              <th className="hidden md:table-cell">Cadence</th>
              <th>Last success</th>
              <th>State</th>
            </tr>
          </thead>
          <tbody>
            {sources.isLoading ? (
              <tr>
                <td colSpan={5} className="py-8 text-center text-xs text-muted-foreground">
                  Loading source registry…
                </td>
              </tr>
            ) : (
              sources.data?.map((source: SourceDefinition) => (
                <tr key={source.id}>
                  <td className="max-w-[260px]">
                    <p className="truncate text-xs font-medium">{source.name}</p>
                    <p className="truncate font-mono text-[10px] text-muted-foreground">{source.code}</p>
                  </td>
                  <td>
                    <Badge variant="outline" className="text-[10px]">
                      {moduleLabel(source.module)}
                    </Badge>
                  </td>
                  <td className="hidden text-[11px] text-muted-foreground md:table-cell">{source.cadence ?? "—"}</td>
                  <td className="text-[11px] text-muted-foreground" title={source.last_success_at ?? undefined}>
                    {source.last_success_at ? fmtRelative(source.last_success_at) : "never"}
                  </td>
                  <td>
                    {source.last_error ? (
                      <Badge className="border border-destructive/40 bg-destructive/15 text-[10px] text-destructive">
                        error
                      </Badge>
                    ) : source.enabled ? (
                      <Badge variant="success" className="text-[10px]">
                        enabled
                      </Badge>
                    ) : (
                      <Badge variant="secondary" className="text-[10px]">
                        paused
                      </Badge>
                    )}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </Panel>
  );
}

function AuditPanel() {
  const audit = useQuery({ queryKey: ["audit"], queryFn: () => api.audit(80) });
  return (
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
  );
}

/** The signed-in user's own alert subscriptions. */
function SubscriptionPanel() {
  const queryClient = useQueryClient();
  const { user } = useAuth();
  const [name, setName] = React.useState("");
  const [modules, setModules] = React.useState<string[]>([]);
  const [sponsors, setSponsors] = React.useState("");
  const [drugs, setDrugs] = React.useState("");
  const [minPriority, setMinPriority] = React.useState(40);
  const [channels, setChannels] = React.useState<string[]>(["dashboard"]);
  const [error, setError] = React.useState<string | null>(null);

  const subscriptions = useQuery({ queryKey: ["subscriptions"], queryFn: () => api.subscriptions() });
  const channelsStatus = useQuery({ queryKey: ["delivery-channels"], queryFn: () => api.deliveryChannels() });
  const configuredChannels = React.useMemo(
    () => (channelsStatus.data?.channels ?? []).filter((c) => c.configured).map((c) => c.name),
    [channelsStatus.data],
  );

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
    <>
      <section className="grid gap-3 sm:grid-cols-3">
        <KpiCard label="Subscriptions" value={subscriptions.data?.length ?? 0} tone="primary" icon={<BellPlus className="h-3.5 w-3.5 text-primary" />} />
        <KpiCard
          label="Delivery channels"
          value={channelsStatus.isLoading ? "…" : `${configuredChannels.length}/${channelsStatus.data?.channels?.length ?? 4}`}
          hint={configuredChannels.length ? configuredChannels.join(" · ") : "dashboard only"}
        />
        <KpiCard label="Access level" value={(user?.role ?? "viewer").replace(/_/g, " ")} tone="success" icon={<ShieldCheck className="h-3.5 w-3.5 text-success" />} />
      </section>

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
                  className={cn(
                    "rounded-full border px-2.5 py-1 text-[11px] transition-colors",
                    modules.includes(module)
                      ? "border-primary/50 bg-primary/15 text-primary"
                      : "border-border/70 text-muted-foreground hover:bg-muted/60",
                  )}
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
              {Object.entries(CHANNEL_META).map(([id, meta]) => {
                const available = configuredChannels.includes(id);
                return (
                  <button
                    key={id}
                    onClick={() => available && setChannels((list) => toggle(list, id))}
                    disabled={!available}
                    title={available ? undefined : "Not configured on this deployment"}
                    className={cn(
                      "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] transition-colors",
                      channels.includes(id) && available
                        ? "border-primary/50 bg-primary/15 text-primary"
                        : "border-border/70 text-muted-foreground hover:bg-muted/60",
                      available ? "" : "cursor-not-allowed opacity-40",
                    )}
                  >
                    {meta.icon}
                    {meta.label}
                    {available ? null : " · off"}
                  </button>
                );
              })}
            </div>
            <p className="text-[10px] text-muted-foreground">
              Channels marked <span className="opacity-70">off</span> are not configured on this deployment;
              the dashboard channel is always active.
            </p>
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
    </>
  );
}

function splitList(value: string): string[] {
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}
