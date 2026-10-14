"use client";

import * as React from "react";
import { useMutation } from "@tanstack/react-query";
import { KeyRound, ShieldCheck } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Panel } from "@/components/common/panel";
import { useAuth } from "@/components/providers/auth-provider";

/**
 * Account settings for the signed-in user: the identity the platform holds and
 * self-service password rotation. This deployment holds a single account, so
 * the page is deliberately small.
 */
export default function AccountPage() {
  const { user } = useAuth();

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-lg font-semibold">Account</h1>
        <p className="text-sm text-muted-foreground">
          The identity signed in to this deployment, and its password.
        </p>
      </div>

      <Panel title="Signed in as" subtitle="The account this deployment holds">
        <dl className="grid gap-3 sm:grid-cols-3">
          <div>
            <dt className="text-[11px] uppercase tracking-wide text-muted-foreground">Email</dt>
            <dd className="text-sm font-medium">{user?.username ?? "—"}</dd>
          </div>
          <div>
            <dt className="text-[11px] uppercase tracking-wide text-muted-foreground">Role</dt>
            <dd className="text-sm font-medium">{user?.role?.replace(/_/g, " ") ?? "—"}</dd>
          </div>
          <div>
            <dt className="text-[11px] uppercase tracking-wide text-muted-foreground">Accounts</dt>
            <dd className="text-sm font-medium">Single-account deployment</dd>
          </div>
        </dl>
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
      icon={<KeyRound className="h-3.5 w-3.5" />}
    >
      <div className="grid gap-3 sm:grid-cols-3">
        <div className="space-y-1.5">
          <label className="text-[11px] text-muted-foreground">Current password</label>
          <Input
            type="password"
            autoComplete="current-password"
            value={current}
            onChange={(e) => setCurrent(e.target.value)}
            className="h-9"
          />
        </div>
        <div className="space-y-1.5">
          <label className="text-[11px] text-muted-foreground">New password</label>
          <Input
            type="password"
            autoComplete="new-password"
            value={next}
            onChange={(e) => setNext(e.target.value)}
            placeholder="At least 8 characters"
            className="h-9"
          />
        </div>
        <div className="space-y-1.5">
          <label className="text-[11px] text-muted-foreground">Confirm new password</label>
          <Input
            type="password"
            autoComplete="new-password"
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            className="h-9"
          />
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
      <p className="mt-3 flex items-center gap-1.5 text-[11px] text-muted-foreground">
        <ShieldCheck className="h-3.5 w-3.5" />
        Changing the password signs out other sessions on next request.
      </p>
    </Panel>
  );
}
