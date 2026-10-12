"use client";

import * as React from "react";
import { Brain, Building2, ChevronDown, Lightbulb, ShieldAlert, Target, Zap } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import { fmtRelative, PRIORITY_STYLES, moduleLabel } from "@/lib/format";
import type { Insight, ScoreComponent } from "@/types/api";

function PriorityBadge({ score, label }: { score: number; label: string }) {
  return (
    <Badge className={cn("border", PRIORITY_STYLES[label] ?? PRIORITY_STYLES.low)}>
      <Zap className="h-3 w-3" />
      {label.toUpperCase()} {Math.round(score)}
    </Badge>
  );
}

/** The engine returns either a flat map or {total, label, components:[...]}. */
function normalizeComponents(
  breakdown: Insight["score_breakdown"],
): Array<{ name: string; points: number; weight?: number; reason?: string | null }> {
  if (!breakdown) return [];
  if (Array.isArray((breakdown as { components?: unknown }).components)) {
    return ((breakdown as { components: ScoreComponent[] }).components ?? []).map((component) => ({
      name: component.name,
      points: Number(component.points ?? 0),
      weight: component.weight,
      reason: component.reason,
    }));
  }
  return Object.entries(breakdown as Record<string, number>)
    .filter(([key]) => key !== "total" && key !== "label")
    .map(([name, points]) => ({ name, points: Number(points) }));
}

export function InsightCard({ insight, defaultOpen }: { insight: Insight; defaultOpen?: boolean }) {
  const [open, setOpen] = React.useState(defaultOpen ?? false);
  const components = normalizeComponents(insight.score_breakdown);
  const companies = insight.affected_companies ?? [];
  const products = insight.affected_products ?? [];

  return (
    <Card className="overflow-hidden">
      <button
        onClick={() => setOpen((value) => !value)}
        className="flex w-full items-start gap-3 p-4 text-left transition-colors hover:bg-muted/30"
      >
        <span className="mt-0.5 grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-primary/12 text-primary ring-1 ring-primary/20">
          <Brain className="h-4 w-4" />
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <PriorityBadge score={insight.priority_score} label={insight.priority_label} />
            <Badge variant="outline">{moduleLabel(insight.module)}</Badge>
            <span className="text-[11px] text-muted-foreground">{fmtRelative(insight.created_at)}</span>
          </div>
          <p className="mt-1.5 truncate text-sm font-medium">{insight.title}</p>
          {insight.what_changed ? (
            <p className="mt-0.5 line-clamp-2 text-xs text-muted-foreground">{insight.what_changed}</p>
          ) : null}
        </div>
        <ChevronDown
          className={cn(
            "mt-1 h-4 w-4 shrink-0 text-muted-foreground transition-transform",
            open && "rotate-180",
          )}
        />
      </button>

      {open ? (
        <div className="animate-fade-in space-y-3 border-t border-border/70 px-4 py-4 text-xs">
          {insight.why_it_matters ? (
            <Section icon={<Lightbulb className="h-3.5 w-3.5" />} title="Why it matters">
              {insight.why_it_matters}
            </Section>
          ) : null}
          {companies.length || products.length ? (
            <div className="grid gap-3 sm:grid-cols-2">
              {companies.length ? (
                <Section icon={<Building2 className="h-3.5 w-3.5" />} title="Affected companies">
                  <div className="flex flex-wrap gap-1">
                    {companies.map((company) => (
                      <Badge key={company} variant="secondary">
                        {company}
                      </Badge>
                    ))}
                  </div>
                </Section>
              ) : null}
              {products.length ? (
                <Section icon={<Target className="h-3.5 w-3.5" />} title="Affected products">
                  <div className="flex flex-wrap gap-1">
                    {products.map((product) => (
                      <Badge key={product} variant="secondary">
                        {product}
                      </Badge>
                    ))}
                  </div>
                </Section>
              ) : null}
            </div>
          ) : null}
          <div className="grid gap-3 sm:grid-cols-2">
            {insight.generic_opportunity ? (
              <Section icon={<Target className="h-3.5 w-3.5" />} title="Generic opportunity">
                {insight.generic_opportunity}
              </Section>
            ) : null}
            {insight.exclusivity_risk ? (
              <Section icon={<ShieldAlert className="h-3.5 w-3.5" />} title="Exclusivity risk">
                {insight.exclusivity_risk}
              </Section>
            ) : null}
          </div>
          {insight.recommended_action ? (
            <div className="rounded-lg border border-primary/25 bg-primary/8 p-3">
              <p className="mb-1 flex items-center gap-1.5 font-medium text-primary">
                <Zap className="h-3.5 w-3.5" /> Recommended action
              </p>
              <p className="text-muted-foreground">{insight.recommended_action}</p>
            </div>
          ) : null}

          {components.length ? (
            <div>
              <p className="mb-1.5 font-medium text-muted-foreground">Score breakdown</p>
              <div className="space-y-1">
                {components.map((component) => {
                  const width = Math.min(100, (component.points / (component.weight || 25)) * 100);
                  return (
                    <div key={component.name} className="flex items-center gap-2">
                      <span className="w-36 shrink-0 truncate text-[11px] text-muted-foreground" title={component.reason ?? undefined}>
                        {component.name.replace(/_/g, " ")}
                      </span>
                      <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-muted">
                        <div
                          className="h-full rounded-full bg-primary"
                          style={{ width: `${width}%` }}
                        />
                      </div>
                      <span className="w-10 text-right tabular-nums text-[11px]">
                        {component.points}
                        {component.weight ? <span className="text-muted-foreground">/{component.weight}</span> : null}
                      </span>
                    </div>
                  );
                })}
              </div>
            </div>
          ) : null}

          <p className="text-[10px] text-muted-foreground">
            Generated by {insight.generated_by ?? "rules-engine"}
            {insight.confidence != null ? ` · confidence ${(insight.confidence * 100).toFixed(0)}%` : ""}
          </p>
        </div>
      ) : null}
    </Card>
  );
}

function Section({
  icon,
  title,
  children,
}: {
  icon: React.ReactNode;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <p className="mb-1 flex items-center gap-1.5 font-medium text-muted-foreground">
        {icon}
        {title}
      </p>
      <div className="text-foreground/90">{children}</div>
    </div>
  );
}
