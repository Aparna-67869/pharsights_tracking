"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { Activity, Database, GitCompareArrows, Loader2, Lock, ShieldCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useAuth } from "@/components/providers/auth-provider";

/**
 * Sign-in only. This is a company-internal platform: there is no public
 * self-registration. Accounts are provisioned by an administrator, so the page
 * exposes a single authentication path.
 */
export default function LoginPage() {
  const { login, user, loading } = useAuth();
  const router = useRouter();
  const [username, setUsername] = React.useState("");
  const [password, setPassword] = React.useState("");
  const [submitting, setSubmitting] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    if (!loading && user) router.replace("/");
  }, [loading, user, router]);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await login(username, password);
    } catch (err) {
      const message = err instanceof Error && err.message ? err.message : "Those credentials were not accepted.";
      setError(message);
    } finally {
      setSubmitting(false);
    }
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
              <p className="text-lg font-semibold">Pharma Intelligence Platform</p>
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
              <span className="font-semibold">Pharma Intelligence</span>
            </div>
            <h2 className="text-lg font-semibold">Sign in</h2>
            <p className="mt-1 text-sm text-muted-foreground">
              Sign in with the account registered for this deployment.
            </p>

            <form onSubmit={submit} className="mt-6 space-y-4">
              <div className="space-y-1.5">
                <label className="text-sm font-medium text-muted-foreground" htmlFor="username">
                  Email
                </label>
                <Input
                  id="username"
                  type="email"
                  autoComplete="username"
                  value={username}
                  onChange={(event) => setUsername(event.target.value)}
                  required
                />
              </div>
              <div className="space-y-1.5">
                <label className="text-sm font-medium text-muted-foreground" htmlFor="password">
                  Password
                </label>
                <Input
                  id="password"
                  type="password"
                  autoComplete="current-password"
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  required
                />
              </div>

              {error ? (
                <p className="rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">
                  {error}
                </p>
              ) : null}

              <Button type="submit" className="w-full" disabled={submitting}>
                {submitting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Lock className="h-4 w-4" />}
                {submitting ? "Signing in…" : "Sign in"}
              </Button>
            </form>

            <p className="mt-4 text-center text-xs text-muted-foreground">
              Need access? Contact your platform administrator.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
