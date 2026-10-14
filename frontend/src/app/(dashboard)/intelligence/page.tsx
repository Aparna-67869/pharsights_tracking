"use client";

import * as React from "react";
import { useQuery } from "@tanstack/react-query";
import { Brain, Sparkles } from "lucide-react";
import { api } from "@/lib/api";
import { Select } from "@/components/ui/input";
import { InsightCard } from "@/components/common/insight-card";
import { EmptyState, TableSkeleton } from "@/components/ui/skeleton";
import { moduleLabel } from "@/lib/format";

const MODULES = ["", "ftf", "pte", "pde", "orange_book"];
const PRIORITIES = ["", "critical", "high", "medium", "low"];

/**
 * Intelligence: the AI impact analysis generated for every material change.
 *
 * This is the actionable output of the monitoring pipeline — what changed, why
 * it matters, who is affected, and the recommended action. Raw baseline
 * ingestion is deliberately not shown here; it carries no signal.
 */
export default function IntelligencePage() {
  const [page, setPage] = React.useState(1);
  const [module, setModule] = React.useState("");
  const [priority, setPriority] = React.useState("");
  React.useEffect(() => setPage(1), [module, priority]);

  const params = {
    page,
    page_size: 20,
    module: module || undefined,
    priority_label: priority || undefined,
  };
  const query = useQuery({ queryKey: ["insights", params], queryFn: () => api.insights(params) });

  return (
    <div className="space-y-4">
      <header>
        <h1 className="flex items-center gap-2 text-lg font-semibold tracking-tight">
          <Brain className="h-4.5 w-4.5 text-primary" /> Intelligence
        </h1>
        <p className="mt-0.5 text-xs text-muted-foreground">
          AI impact analysis for every material change across FTF, PTE, PDE and the Orange Book —
          what changed, why it matters, and the recommended action.
        </p>
      </header>

      <div className="flex flex-wrap items-center gap-2">
        <Select value={module} onChange={(event) => setModule(event.target.value)} className="h-8 w-48 text-xs">
          {MODULES.map((option) => (
            <option key={option} value={option}>
              {option ? moduleLabel(option) : "All modules"}
            </option>
          ))}
        </Select>
        <Select value={priority} onChange={(event) => setPriority(event.target.value)} className="h-8 w-40 text-xs">
          {PRIORITIES.map((option) => (
            <option key={option} value={option}>
              {option ? option[0].toUpperCase() + option.slice(1) : "All priorities"}
            </option>
          ))}
        </Select>
        <span className="ml-auto text-xs text-muted-foreground">
          {query.data?.total ?? 0} insight{(query.data?.total ?? 0) === 1 ? "" : "s"}
        </span>
      </div>

      {query.isLoading ? (
        <TableSkeleton rows={6} cols={1} />
      ) : (query.data?.items.length ?? 0) === 0 ? (
        <EmptyState
          icon={<Sparkles className="h-8 w-8" />}
          title="No impact analyses yet"
          description="Insights are raised only for material changes. The first load of a source is baseline data, so it never produces an insight — analysis appears as soon as a regulator publishes a change."
        />
      ) : (
        <>
          {query.data?.items.map((insight, index) => (
            <InsightCard key={insight.id} insight={insight} defaultOpen={index === 0 && page === 1} />
          ))}
          <div className="flex items-center justify-between pt-1 text-xs text-muted-foreground">
            <span>
              Page {query.data?.page} of {query.data?.pages}
            </span>
            <div className="flex gap-2">
              <button
                disabled={page <= 1}
                onClick={() => setPage((value) => value - 1)}
                className="rounded-md border border-border px-3 py-1.5 disabled:opacity-40"
              >
                Prev
              </button>
              <button
                disabled={page >= (query.data?.pages ?? 1)}
                onClick={() => setPage((value) => value + 1)}
                className="rounded-md border border-border px-3 py-1.5 disabled:opacity-40"
              >
                Next
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
