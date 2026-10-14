"use client";

import * as React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Activity,
  Database,
  ShieldCheck,
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
import type { SourceDefinition } from "@/types/api";

const ROLES = ["admin", "analyst", "regulatory_affairs", "ip_counsel", "executive", "viewer"];

/**
 * Administration: account management (administrators), the live source
 * registry and the platform audit trail.
 *
 * Everything added here is written to the database and read back through the
 * API, so an account or role change is immediately visible in the tables on
 * this page.
 */
export default function AdminPage() {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const channelsStatus = useQuery({ queryKey: ["delivery-channels"], queryFn: () => api.deliveryChannels() });
  const configuredChannels = React.useMemo(
    () => (channelsStatus.data?.channels ?? []).filter((c) => c.configured).map((c) => c.name),
    [channelsStatus.data],
  );

  return (
    <div className="space-y-4">
      <header>
        <h1 className="flex items-center gap-2 text-lg font-semibold tracking-tight">
          <ShieldCheck className="h-4.5 w-4.5 text-primary" /> Administration
        </h1>
        <p className="mt-0.5 text-xs text-muted-foreground">
          Manage platform accounts, the monitored source registry and the audit trail.
        </p>
      </header>

      <section className="grid gap-3 sm:grid-cols-2">
        <KpiCard
          label="Delivery channels"
          value={channelsStatus.isLoading ? "…" : `${configuredChannels.length}/${channelsStatus.data?.channels?.length ?? 4}`}
          hint={configuredChannels.length ? configuredChannels.join(" · ") : "dashboard only"}
        />
        <KpiCard label="Access level" value={(user?.role ?? "viewer").replace(/_/g, " ")} tone="success" icon={<ShieldCheck className="h-3.5 w-3.5 text-success" />} />
      </section>

      <AdminTabs isAdmin={isAdmin} />
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
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const users = useQuery({ queryKey: ["users"], queryFn: () => api.users() });
  const [fullName, setFullName] = React.useState("");
  const [email, setEmail] = React.useState("");
  const [password, setPassword] = React.useState("");
  const [error, setError] = React.useState<string | null>(null);
  const canCreate = user?.can_create_accounts ?? true;

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
        title={canCreate ? "Add account" : "Single-account deployment"}
        subtitle={
          canCreate
            ? "Provisioned accounts can sign in immediately"
            : "This deployment accepts one account only"
        }
        icon={<UserPlus className="h-3.5 w-3.5" />}
      >
        {canCreate ? (
          <>
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
          </>
        ) : (
          <p className="text-[11px] text-muted-foreground">
            Only{" "}
            <span className="font-medium text-foreground">{user?.allowed_login_email}</span>{" "}
            may sign in to this platform. Creating further accounts is disabled, and that account
            cannot be deactivated. Set <span className="font-mono">BLOCK_ADDITIONAL_ACCOUNTS=false</span>{" "}
            on the API to re-enable multi-account provisioning.
          </p>
        )}
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

      <ChangePasswordPanel />
    </div>
  );
}

/** Self-service password change for the signed-in account. */
function ChangePasswordPanel() {
  const [current, setCurrent] = React.useState("");
  const [next, setNext] = React.useState("");
  const [confirm, setConfirm] = React.useState("");
  const [message, setMessage] = React.useState<string | null>(null);
  const [error, setError] = React.useState<string | null>(null);

  const change = useMutation({
    mutationFn: () => api.changePassword({ current_password: current, new_password: next }),
    onSuccess: () => {
      setCurrent("");
      setNext("");
      setConfirm("");
      setError(null);
      setMessage("Password updated.");
    },
    onError: (err: Error) => {
      setMessage(null);
      setError(err instanceof ApiError ? err.message : "Could not change the password.");
    },
  });

  const mismatch = confirm.length > 0 && next !== confirm;
  const canSubmit = current.length > 0 && next.length >= 8 && next === confirm && !change.isPending;

  return (
    <Panel
      title="Change password"
      subtitle="Rotate the password for the signed-in account"
      icon={<ShieldCheck className="h-3.5 w-3.5" />}
    >
      <div className="grid gap-3 sm:grid-cols-3">
        <div className="space-y-1.5">
          <label className="text-[11px] text-muted-foreground">Current password</label>
          <Input type="password" value={current} onChange={(e) => setCurrent(e.target.value)} className="h-9" />
        </div>
        <div className="space-y-1.5">
          <label className="text-[11px] text-muted-foreground">New password</label>
          <Input type="password" value={next} onChange={(e) => setNext(e.target.value)} placeholder="At least 8 characters" className="h-9" />
        </div>
        <div className="space-y-1.5">
          <label className="text-[11px] text-muted-foreground">Confirm new password</label>
          <Input type="password" value={confirm} onChange={(e) => setConfirm(e.target.value)} className="h-9" />
        </div>
      </div>
      <div className="mt-3 flex items-center gap-3">
        <Button className="h-9" disabled={!canSubmit} onClick={() => change.mutate()}>
          {change.isPending ? "Updating…" : "Update password"}
        </Button>
        {mismatch ? <p className="text-[11px] text-destructive">Passwords do not match.</p> : null}
        {error ? <p className="text-[11px] text-destructive">{error}</p> : null}
        {message ? <p className="text-[11px] text-success">{message}</p> : null}
      </div>
    </Panel>
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

