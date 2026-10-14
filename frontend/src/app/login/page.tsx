"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import {
  Activity,
  Database,
  GitCompareArrows,
  Loader2,
  Lock,
  ShieldCheck,
  UserPlus,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/components/providers/auth-provider";

/**
 * Sign-in and account creation.
 *
 * This deployment is single-account: the platform accepts exactly one address,
 * which is created here on first use and then signed in with. The email field
 * is therefore fixed to that address when the API reports one; if the account
 * already exists, creation is refused and the user is pointed at sign-in.
 */
export default function LoginPage() {
  const { login, user, loading } = useAuth();
  const router = useRouter();
  const [mode, setMode] = React.useState<"signin" | "create">("signin");
  const [username, setUsername] = React.useState("");
  const [fullName, setFullName] = React.useState("");
  const [password, setPassword] = React.useState("");
  const [submitting, setSubmitting] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [notice, setNotice] = React.useState<string | null>(null);
  const [allowedEmail, setAllowedEmail] = React.useState<string | null>(null);

  React.useEffect(() => {
    if (!loading && user) router.replace("/");
  }, [loading, user, router]);

  // The API tells us the one address this deployment accepts, so the create
  // form can be pre-filled rather than guessed. This endpoint is public, so it
  // works before anyone has signed in.
  React.useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const config = await api.authConfig();
        if (!cancelled) setAllowedEmail(config.allowed_login_email);
      } catch {
        /* nothing to prefill */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setError(null);
    setNotice(null);
    setSubmitting(true);
    try {
      if (mode === "signin") {
        await login(username, password);
        return;
      }
      await api.register({
        full_name: fullName,
        email: allowedEmail ?? username,
        password,
      });
      setNotice("Account created. Signing you in…");
      await login(allowedEmail ?? username, password);
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        setError("That account already exists. Switch to Sign in and use your password.");
        setMode("signin");
      } else {
        setError(err instanceof Error && err.message ? err.message : "Something went wrong.");
      }
    } finally {
      setSubmitting(false);
    }
  };

  const switchMode = (next: "signin" | "create") => {
    setMode(next);
    setError(null);
    setNotice(null);
  };

  return (
    <div className="grid-backdrop relative min-h-screen">
      <div className="absolute inset-0 bg-gradient-to-br from-background via-background/95 to-primary/10" />
      <div className="relative z-10 grid min-h-screen lg:grid-cols-2">
        <div className="hidden flex-col justify-between p-12 lg:flex">
          <div className="flex items-center gap-3">
            <span className="grid h-11 w-11 place-items-center rounded-xl bg-primary/15 text-primary ring-1 ring-primary/25">
              <ShieldCheck className="h-6 w-6" />
            </span>
            <div>
              <p className="text-lg font-semibold">Pharsights Intel Command Center</p>
              <p className="text-xs text-muted-foreground">Regulatory Intelligence Command Center</p>
            </div>
          </div>

          <div className="max-w-lg space-y-6">
            <h1 className="text-3xl font-semibold leading-tight">
              Every FDA, USPTO and Orange Book change — detected, scored and explained before you ask.
            </h1>
            <p className="text-sm text-muted-foreground">
              Continuous monitoring of Paragraph IV certifications, patent term extensions, approved
              active moieties and Orange Book supplements, with AI impact analysis and real-time
              alerting.
            </p>
            <ul className="space-y-3 text-sm">
              {[
                { icon: GitCompareArrows, text: "Version-diffed First-to-File and PTE registers" },
                { icon: Database, text: "360° drug, patent and sponsor knowledge graph" },
                { icon: Activity, text: "Priority-scored alerts, not noise" },
              ].map(({ icon: Icon, text }) => (
                <li key={text} className="flex items-center gap-3 text-muted-foreground">
                  <span className="grid h-8 w-8 place-items-center rounded-lg bg-surface/70 ring-1 ring-border/70">
                    <Icon className="h-4 w-4 text-primary" />
                  </span>
                  {text}
                </li>
              ))}
            </ul>
          </div>

          <p className="text-xs text-muted-foreground">
            Data derived from public FDA and USPTO sources. Not legal advice.
          </p>
        </div>

        <div className="flex items-center justify-center p-6">
          <div className="glass-strong w-full max-w-sm rounded-2xl p-7">
            <div className="mb-6 flex items-center gap-2 lg:hidden">
              <ShieldCheck className="h-5 w-5 text-primary" />
              <span className="font-semibold">Pharsights Intel Command Center</span>
            </div>

            <div className="mb-5 grid grid-cols-2 gap-1 rounded-lg bg-muted/40 p-1">
              <button
                type="button"
                onClick={() => switchMode("signin")}
                className={
                  "rounded-md px-3 py-1.5 text-sm transition-colors " +
                  (mode === "signin" ? "bg-panel font-medium shadow-sm" : "text-muted-foreground")
                }
              >
                Sign in
              </button>
              <button
                type="button"
                onClick={() => switchMode("create")}
                className={
                  "rounded-md px-3 py-1.5 text-sm transition-colors " +
                  (mode === "create" ? "bg-panel font-medium shadow-sm" : "text-muted-foreground")
                }
              >
                Create account
              </button>
            </div>

            <h2 className="text-lg font-semibold">
              {mode === "signin" ? "Sign in" : "Create your account"}
            </h2>
            <p className="mt-1 text-sm text-muted-foreground">
              {mode === "signin"
                ? "Sign in to the platform."
                : "This deployment holds a single account. Create it once with the address below."}
            </p>

            <form onSubmit={submit} className="mt-6 space-y-4">
              {mode === "create" ? (
                <div className="space-y-1.5">
                  <label className="text-sm font-medium text-muted-foreground" htmlFor="full_name">
                    Full name
                  </label>
                  <Input
                    id="full_name"
                    autoComplete="name"
                    value={fullName}
                    onChange={(event) => setFullName(event.target.value)}
                    required
                  />
                </div>
              ) : null}

              <div className="space-y-1.5">
                <label className="text-sm font-medium text-muted-foreground" htmlFor="username">
                  Email
                </label>
                {mode === "create" && allowedEmail ? (
                  <Input id="username" type="email" value={allowedEmail} readOnly className="opacity-80" />
                ) : (
                  <Input
                    id="username"
                    type="email"
                    autoComplete="username"
                    value={username}
                    onChange={(event) => setUsername(event.target.value)}
                    required
                  />
                )}
              </div>

              <div className="space-y-1.5">
                <label className="text-sm font-medium text-muted-foreground" htmlFor="password">
                  Password
                </label>
                <Input
                  id="password"
                  type="password"
                  autoComplete={mode === "signin" ? "current-password" : "new-password"}
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  minLength={mode === "create" ? 8 : undefined}
                  placeholder={mode === "create" ? "At least 8 characters" : undefined}
                  required
                />
              </div>

              {error ? (
                <p className="rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">
                  {error}
                </p>
              ) : null}
              {notice ? (
                <p className="rounded-md border border-success/30 bg-success/10 px-3 py-2 text-sm text-success">
                  {notice}
                </p>
              ) : null}

              <Button type="submit" className="w-full" disabled={submitting}>
                {submitting ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : mode === "signin" ? (
                  <Lock className="h-4 w-4" />
                ) : (
                  <UserPlus className="h-4 w-4" />
                )}
                {submitting
                  ? mode === "signin"
                    ? "Signing in…"
                    : "Creating account…"
                  : mode === "signin"
                    ? "Sign in"
                    : "Create account"}
              </Button>
            </form>

            {mode === "create" ? (
              <p className="mt-4 text-center text-xs text-muted-foreground">
                Already created? Switch to Sign in.
              </p>
            ) : null}
          </div>
        </div>
      </div>
    </div>
  );
}
