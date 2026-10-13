"use client";

import * as React from "react";
import { cn } from "@/lib/utils";

/**
 * The command-center surface primitive. Every dashboard region is a Panel so
 * spacing, borders and headers stay identical across modules.
 */
export function Panel({
  title,
  subtitle,
  icon,
  actions,
  children,
  className,
  bodyClassName,
  tone = "default",
  live,
}: {
  title?: React.ReactNode;
  subtitle?: React.ReactNode;
  icon?: React.ReactNode;
  actions?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
  bodyClassName?: string;
  tone?: "default" | "primary" | "success" | "warning" | "destructive";
  live?: boolean;
}) {
  const accent: Record<string, string> = {
    default: "bg-muted-foreground/50",
    primary: "bg-primary",
    success: "bg-success",
    warning: "bg-warning",
    destructive: "bg-destructive",
  };
  return (
    <section className={cn("panel flex flex-col overflow-hidden", className)}>
      {title ? (
        <header className="panel-head">
          <span className={cn("h-3.5 w-0.5 rounded-full", accent[tone])} />
          {icon ? <span className="text-muted-foreground">{icon}</span> : null}
          <div className="min-w-0 flex-1">
            <h3 className="panel-title">{title}</h3>
            {subtitle ? (
              <p className="mt-0.5 truncate text-[11px] normal-case tracking-normal text-muted-foreground/80">
                {subtitle}
              </p>
            ) : null}
          </div>
          {live ? (
            <span className="flex items-center gap-1.5 text-[10px] font-medium uppercase tracking-wider text-success">
              <span className="live-dot" /> live
            </span>
          ) : null}
          {actions ? <div className="flex items-center gap-1.5">{actions}</div> : null}
        </header>
      ) : null}
      <div className={cn("flex-1", bodyClassName ?? "p-3")}>{children}</div>
    </section>
  );
}
