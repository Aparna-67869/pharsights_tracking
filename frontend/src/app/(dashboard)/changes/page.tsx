"use client";

import * as React from "react";
import { useQuery } from "@tanstack/react-query";
import { Activity, Brain, History } from "lucide-react";
import { api } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Select } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { DataTable, type Column } from "@/components/tables/data-table";
import { InsightCard } from "@/components/common/insight-card";
import { EmptyState, TableSkeleton } from "@/components/ui/skeleton";
import { CHANGE_STYLES, fmtDateTime, fmtRelative, moduleLabel } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { DetectedChange, Insight } from "@/types/api";

const MODULES = ["", "ftf", "pte", "pde", "orange_book"];
const CHANGE_TYPES = ["", "added", "updated", "removed"];

export default function ChangesPage() {
  const [tab, setTab] = React.useState("insights");
  return (
    <div className="space-y-5">
      <header>
        <h1 className="flex items-center gap-2 text-xl font-semibold">
          <Activity className="h-5 w-5 text-primary" /> Change History &amp; Intelligence
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">
          The complete audit trail of every detected source delta, with the AI impact analysis generated for
          each material change.
        </p>
      </header>

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList>
          <TabsTrigger value="insights">
            <Brain className="h-3.5 w-3.5" /> AI Insights
          </TabsTrigger>
          <TabsTrigger value="changes">
            <History className="h-3.5 w-3.5" /> Audit Trail
          </TabsTrigger>
        </TabsList>
        <TabsContent value="insights" className="mt-4">
          <InsightsPanel />
        </TabsContent>
        <TabsContent value="changes" className="mt-4">
          <ChangesPanel />
        </TabsContent>
      </Tabs>
    </div>
  );
}

function InsightsPanel() {
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

  if (query.isLoading) return <TableSkeleton rows={6} cols={1} />;

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <Select value={module} onChange={(event) => setModule(event.target.value)} className="h-8 w-48 text-xs">
          {MODULES.map((option) => (
            <option key={option} value={option}>
              {option ? moduleLabel(option) : "All modules"}
            </option>
          ))}
        </Select>
        <Select value={priority} onChange={(event) => setPriority(event.target.value)} className="h-8 w-40 text-xs">
          {["", "critical", "high", "medium", "low"].map((option) => (
            <option key={option} value={option}>
              {option ? option[0].toUpperCase() + option.slice(1) : "All priorities"}
            </option>
          ))}
        </Select>
        <span className="ml-auto text-xs text-muted-foreground">
          {query.data?.total ?? 0} insight{(query.data?.total ?? 0) === 1 ? "" : "s"}
        </span>
      </div>

      {(query.data?.items.length ?? 0) === 0 ? (
        <EmptyState
          icon={<Brain className="h-8 w-8" />}
          title="No insights match these filters"
          description="Insights are generated only for material changes. Baseline ingestion is recorded in the audit trail but never scored."
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

function ChangesPanel() {
  const [page, setPage] = React.useState(1);
  const [module, setModule] = React.useState("");
  const [changeType, setChangeType] = React.useState("");
  const [includeBaseline, setIncludeBaseline] = React.useState(false);
  React.useEffect(() => setPage(1), [module, changeType, includeBaseline]);

  const params = {
    page,
    page_size: 50,
    module: module || undefined,
    change_type: changeType || undefined,
    include_baseline: includeBaseline || undefined,
  };
  const query = useQuery({ queryKey: ["changes", params], queryFn: () => api.changes(params) });

  const columns: Column<DetectedChange>[] = [
    {
      key: "change_type",
      header: "Type",
      render: (row) => (
        <Badge className={cn("border", CHANGE_STYLES[row.change_type] ?? "")}>{row.change_type}</Badge>
      ),
    },
    { key: "module", header: "Module", render: (row) => moduleLabel(row.module) },
    { key: "entity_type", header: "Entity", render: (row) => <span className="font-mono text-xs">{row.entity_type}</span> },
    {
      key: "source_key",
      header: "Record",
      render: (row) => <span className="block max-w-[380px] truncate text-xs">{row.source_key}</span>,
    },
    { key: "source_code", header: "Source", render: (row) => <span className="font-mono text-[11px]">{row.source_code}</span> },
    {
      key: "detected_at",
      header: "Detected",
      render: (row) => (
        <div>
          <p className="tabular-nums">{fmtDateTime(row.detected_at)}</p>
          <p className="text-[10px] text-muted-foreground">{fmtRelative(row.detected_at)}</p>
        </div>
      ),
    },
    {
      key: "is_baseline",
      header: "Baseline",
      render: (row) => (row.is_baseline ? <Badge variant="secondary">baseline</Badge> : <Badge variant="success">delta</Badge>),
    },
  ];

  return (
    <DataTable<DetectedChange>
      title="Detected change audit trail"
      description="Immutable record of added, updated and removed rows across every monitored source"
      columns={columns}
      rows={query.data?.items ?? []}
      total={query.data?.total ?? 0}
      page={query.data?.page ?? 1}
      pageSize={query.data?.page_size ?? 50}
      pages={query.data?.pages ?? 1}
      loading={query.isLoading}
      error={query.error ? (query.error as Error).message : null}
      onPageChange={setPage}
      onRefresh={() => void query.refetch()}
      exportPath="/changes/export"
      exportParams={{ module: module || undefined, include_baseline: includeBaseline || undefined }}
      filters={
        <>
          <Select value={module} onChange={(event) => setModule(event.target.value)} className="h-8 w-44 text-xs">
            {MODULES.map((option) => (
              <option key={option} value={option}>
                {option ? moduleLabel(option) : "All modules"}
              </option>
            ))}
          </Select>
          <Select value={changeType} onChange={(event) => setChangeType(event.target.value)} className="h-8 w-36 text-xs">
            {CHANGE_TYPES.map((option) => (
              <option key={option} value={option}>
                {option ? option[0].toUpperCase() + option.slice(1) : "All change types"}
              </option>
            ))}
          </Select>
          <label className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
            <input
              type="checkbox"
              checked={includeBaseline}
              onChange={(event) => setIncludeBaseline(event.target.checked)}
              className="h-3.5 w-3.5 rounded border-border"
            />
            Include baseline snapshot
          </label>
        </>
      }
    />
  );
}
