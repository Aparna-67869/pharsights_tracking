"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { Activity, Database, GitCompareArrows, Loader2, Lock, ShieldCheck, UserPlus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useAuth } from "@/components/providers/auth-provider";

const DEMO_ACCOUNTS = [
  { label: "Executive", email: "exec@pharma-intel.local", password: "ExecPass!234" },
  { label: "Analyst", email: "analyst@pharma-intel.local", password: "AnalystPass!234" },
  { label: "Viewer", email: "viewer@pharma-intel.local", password: "ViewerPass!234" },
];

export default function LoginPage() {
  const { login, register, user, loading } = useAuth();
  const router = useRouter();
  const [mode, setMode] = React.useState<"signin" | "signup">("signin");
  const [username, setUsername] = React.useState("");
  const [fullName, setFullName] = React.useState("");
  const [confirm, setConfirm] = React.useState("");
  const [password, setPassword] = React.useState("");
  const [submitting, setSubmitting] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [showDemo, setShowDemo] = React.useState(false);

  const isSignup = mode === "signup";

  React.useEffect(() => {
    if (!loading && user) router.replace("/");
  }, [loading, user, router]);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setError(null);
    if (isSignup && password !== confirm) {
      setError("The two passwords do not match.");
      return;
    }
    setSubmitting(true);
    try {
      if (isSignup) {
        await register({ full_name: fullName.trim(), email: username.trim(), password });
      } else {
        await login(username, password);
      }
    } catch (err) {
      const message =
        err instanceof Error && err.message
          ? err.message
          : isSignup
            ? "Account creation failed."
            : "Those credentials were not accepted.";
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

          <p className="text-[11px] text-muted-foreground">
            Data derived from public FDA and USPTO sources. Not legal advice.
          </p>
        </div>

        <div className="flex items-center justify-center p-6">
          <div className="glass-strong w-full max-w-sm rounded-2xl p-7">
            <div className="mb-6 flex items-center gap-2 lg:hidden">
              <ShieldCheck className="h-5 w-5 text-primary" />
              <span className="font-semibold">Pharma Intelligence</span>
            </div>
            <h2 className="text-lg font-semibold">{isSignup ? "Create your account" : "Sign in"}</h2>
            <p className="mt-1 text-xs text-muted-foreground">
              {isSignup
                ? "New accounts start read-only. An administrator can elevate your role."
                : "Use your enterprise credentials to access the command center."}
            </p>

            <form onSubmit={submit} className="mt-6 space-y-4">
              {isSignup ? (
                <div className="space-y-1.5">
                  <label className="text-xs font-medium text-muted-foreground" htmlFor="fullName">
                    Full name
                  </label>
                  <Input
                    id="fullName"
                    autoComplete="name"
                    value={fullName}
                    onChange={(event) => setFullName(event.target.value)}
                    required
                  />
                </div>
              ) : null}
              <div className="space-y-1.5">
                <label className="text-xs font-medium text-muted-foreground" htmlFor="username">
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
                <label className="text-xs font-medium text-muted-foreground" htmlFor="password">
                  Password
                </label>
                <Input
                  id="password"
                  type="password"
                  autoComplete={isSignup ? "new-password" : "current-password"}
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  minLength={isSignup ? 8 : undefined}
                  required
                />
                {isSignup ? (
                  <p className="text-[11px] text-muted-foreground">At least 8 characters.</p>
                ) : null}
              </div>
              {isSignup ? (
                <div className="space-y-1.5">
                  <label className="text-xs font-medium text-muted-foreground" htmlFor="confirm">
                    Confirm password
                  </label>
                  <Input
                    id="confirm"
                    type="password"
                    autoComplete="new-password"
                    value={confirm}
                    onChange={(event) => setConfirm(event.target.value)}
                    minLength={8}
                    required
                  />
                </div>
              ) : null}

              {error ? (
                <p className="rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-xs text-destructive">
                  {error}
                </p>
              ) : null}

              <Button type="submit" className="w-full" disabled={submitting}>
                {submitting ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : isSignup ? (
                  <UserPlus className="h-4 w-4" />
                ) : (
                  <Lock className="h-4 w-4" />
                )}
                {submitting ? (isSignup ? "Creating account…" : "Signing in…") : isSignup ? "Create account" : "Sign in"}
              </Button>
            </form>

            <p className="mt-4 text-center text-xs text-muted-foreground">
              {isSignup ? "Already have an account?" : "New to the platform?"}{" "}
              <button
                type="button"
                onClick={() => {
                  setMode(isSignup ? "signin" : "signup");
                  setError(null);
                }}
                className="font-medium text-primary underline-offset-2 hover:underline"
              >
                {isSignup ? "Sign in" : "Create an account"}
              </button>
            </p>

            {!isSignup ? (
            <div className="mt-6 border-t border-border/70 pt-4">
              <button
                type="button"
                onClick={() => setShowDemo((v) => !v)}
                className="text-[11px] font-medium text-muted-foreground underline-offset-2 hover:text-foreground hover:underline"
              >
                {showDemo ? "Hide demo accounts" : "Looking for a demo account?"}
              </button>
              {showDemo ? (
                <div className="mt-3 rounded-lg border border-border/70 bg-muted/30 p-3">
                  <p className="mb-2 text-[11px] leading-relaxed text-muted-foreground">
                    For evaluation only. These accounts exist only when the platform is seeded with
                    development data, and are not present in a production deployment.
                  </p>
                  <div className="flex flex-wrap gap-1.5">
                    {DEMO_ACCOUNTS.map((account) => (
                      <button
                        key={account.email}
                        type="button"
                        onClick={() => {
                          setUsername(account.email);
                          setPassword(account.password);
                        }}
                        className="rounded-md border border-border/70 px-2 py-1 text-[11px] text-muted-foreground transition-colors hover:bg-muted/60 hover:text-foreground"
                      >
                        {account.label}
                      </button>
                    ))}
                  </div>
                </div>
              ) : null}
            </div>
            ) : null}
          </div>
        </div>
      </div>
    </div>
  );
}
