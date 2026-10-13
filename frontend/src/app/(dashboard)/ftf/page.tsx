"use client";

import * as React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CloudDownload, GitCompareArrows, Info, RefreshCw } from "lucide-react";
import { api } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input, Select } from "@/components/ui/input";
import { DataTable, type Column } from "@/components/tables/data-table";
import { AreaTrend, BarSeries } from "@/components/charts/charts";
import { KpiCard } from "@/components/common/kpi-card";
import { OfficialSourceBanner } from "@/components/common/official-source-banner";
import { SourceProvenance } from "@/components/common/source-provenance";
import { SourceCells } from "@/components/common/source-cells";
import { fmtDate, fmtNumber, daysUntil, rawValue } from "@/lib/format";
import { useDebounced } from "@/hooks/use-debounce";
import { useAuth } from "@/components/providers/auth-provider";
import type { FtfRecord } from "@/types/api";

const STATUS_OPTIONS = ["", "eligible", "extinguished", "deferred"];

export default function FtfPage() {
  const queryClient = useQueryClient();
  const { hasScope } = useAuth();
  const canRun = hasScope("run:pipeline");
  const [page, setPage] = React.useState(1);
  const [search, setSearch] = React.useState("");
  const [status, setStatus] = React.useState("");
  const [expiringBefore, setExpiringBefore] = React.useState("");
  const [sort, setSort] = React.useState("drug");
  const debouncedSearch = useDebounced(search, 350);

  React.useEffect(() => setPage(1), [debouncedSearch, status, expiringBefore, sort]);

  const params = {
    page,
    page_size: 50,
    q: debouncedSearch || undefined,
    status: status || undefined,
    expiring_before: expiringBefore || undefined,
    sort,
  };

  const records = useQuery({
    queryKey: ["ftf-records", params],
    queryFn: () => api.ftfRecords(params),
  });
  const summary = useQuery({ queryKey: ["ftf-summary"], queryFn: () => api.ftfSummary() });
  const trend = useQuery({ queryKey: ["ftf-trend"], queryFn: () => api.ftfMonthlyTrend(48) });

  // "Refresh" must actually re-sync from FDA, not just re-read our own API.
  const resync = useMutation({
    mutationFn: () => api.triggerPipeline({ modules: ["ftf"] }),
    onSuccess: () => {
      setTimeout(() => {
        void queryClient.invalidateQueries({ queryKey: ["ftf-records"] });
        void queryClient.invalidateQueries({ queryKey: ["ftf-summary"] });
        void queryClient.invalidateQueries({ queryKey: ["ftf-trend"] });
        void queryClient.invalidateQueries({ queryKey: ["module-source", "ftf"] });
        void queryClient.invalidateQueries({ queryKey: ["pipeline-runs"] });
      }, 2500);
    },
  });

  const columns: Column<FtfRecord>[] = [
    {
      key: "drug_name",
      header: "Drug name",
      render: (row) => (
        <div className="min-w-0">
          <p className="truncate font-medium">{rawValue(row, "Drug Name", "drug_name") ?? "—"}</p>
          <p className="truncate text-[11px] text-muted-foreground">
            {[rawValue(row, "Dosage Form", "dosage_form"), rawValue(row, "Strength", "strength")]
              .filter(Boolean)
              .join(" · ") || "—"}
          </p>
        </div>
      ),
    },
    {
      key: "rld_nda",
      header: "RLD / NDA",
      render: (row) => (
        <span className="tabular-nums">{rawValue(row, "RLD/NDA", "rld_nda") ?? "—"}</span>
      ),
    },
    {
      key: "number_of_andas",
      header: "ANDAs",
      align: "right",
      render: (row) => (row.number_of_andas != null ? fmtNumber(row.number_of_andas) : "—"),
    },
    {
      key: "exclusivity_status",
      header: "Exclusivity status",
      render: (row) =>
        row.exclusivity_status ? (
          <Badge
            variant={
              row.exclusivity_status.toLowerCase() === "eligible"
                ? "success"
                : row.exclusivity_status.toLowerCase() === "extinguished"
                  ? "destructive"
                  : "secondary"
            }
          >
            {row.exclusivity_status}
          </Badge>
        ) : (
          "—"
        ),
    },
    { key: "date_of_submission", header: "Submitted", render: (row) => fmtDate(row.date_of_submission) },
    { key: "decision_posting_date", header: "Decision posted", render: (row) => fmtDate(row.decision_posting_date) },
    {
      key: "last_qualifying_patent_expiry",
      header: "Last patent expiry",
      render: (row) => {
        const days = daysUntil(row.last_qualifying_patent_expiry);
        return (
          <div>
            <span className="tabular-nums">
              {rawValue(row, "Expiration Date of Last Qualifying Patent", "last_qualifying_patent_expiry") ?? "—"}
            </span>
            {days != null ? (
              <span className={days <= 730 ? "ml-1 text-[10px] text-warning-foreground dark:text-amber-300" : "ml-1 text-[10px] text-muted-foreground"}>
                {days > 0 ? `${(days / 365).toFixed(1)}y` : "expired"}
              </span>
            ) : null}
          </div>
        );
      },
    },
  ];

  return (
    <div className="space-y-5">
      <header className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <h1 className="flex items-center gap-2 text-xl font-semibold">
            <GitCompareArrows className="h-5 w-5 text-primary" /> First-to-File (Paragraph IV)
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            FDA patent certifications with 180-day exclusivity status, automatically version-diffed on every
            release of the FDA Paragraph IV list.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button variant="outline" onClick={() => void records.refetch()} disabled={records.isFetching}>
            <RefreshCw className={records.isFetching ? "h-4 w-4 animate-spin" : "h-4 w-4"} /> Reload view
          </Button>
          {canRun ? (
            <Button
              onClick={() => resync.mutate()}
              disabled={resync.isPending}
              title="Re-download the latest FDA list and diff it against the previous snapshot"
            >
              <CloudDownload className={resync.isPending ? "h-4 w-4 animate-pulse" : "h-4 w-4"} />
              {resync.isPending ? "Syncing from FDA…" : "Sync from FDA"}
            </Button>
          ) : null}
        </div>
      </header>

      <OfficialSourceBanner module="ftf" />

      <SourceProvenance module="ftf" />

      <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {summary.data ? (
          <>
            <KpiCard label="Total filings" value={summary.data.total_filings} tone="primary" />
            <KpiCard label="Exclusivity eligible" value={summary.data.eligible_180_day} tone="success" />
            <KpiCard label="Extinguished" value={summary.data.extinguished_180_day} tone="destructive" />
            <KpiCard label="Deferred" value={summary.data.deferred} tone="warning" />
          </>
        ) : null}
      </section>

      <section className="grid gap-4 xl:grid-cols-3">
        {trend.data ? (
          <div className="xl:col-span-2">
            <AreaTrend
              title="Paragraph IV filing trend"
              subtitle="Filings by month of submission (48 months)"
              data={trend.data}
              xKey="month"
              yKey="count"
            />
          </div>
        ) : null}
        {summary.data ? (
          <BarSeries
            title="180-day exclusivity outcome"
            subtitle="Filings by status in the current FDA list"
            data={[
              { status: "Eligible", count: summary.data.eligible_180_day },
              { status: "Extinguished", count: summary.data.extinguished_180_day },
              { status: "Deferred", count: summary.data.deferred },
            ]}
            xKey="status"
            bars={[{ key: "count", label: "Filings" }]}
            height={260}
          />
        ) : null}
      </section>

      <DataTable<FtfRecord>
        title="Paragraph IV certifications"
        description="Filter, inspect and export the current FDA list"
        columns={columns}
        rows={records.data?.items ?? []}
        total={records.data?.total ?? 0}
        page={records.data?.page ?? 1}
        pageSize={records.data?.page_size ?? 50}
        pages={records.data?.pages ?? 1}
        loading={records.isLoading}
        error={records.error ? (records.error as Error).message : null}
        onPageChange={setPage}
        onRefresh={() => void records.refetch()}
        onSearch={setSearch}
        searchPlaceholder="Search drug, brand or NDA…"
        exportPath="/ftf/export"
        exportParams={{ q: debouncedSearch || undefined, status: status || undefined }}
        renderDetail={(row) => <SourceCells raw={row.raw} />}
        filters={
          <>
            <Select
              value={sort}
              onChange={(event) => setSort(event.target.value)}
              className="h-8 w-44 text-xs"
              aria-label="Sort order"
            >
              <option value="drug">A–Z (FDA list order)</option>
              <option value="submitted">Newest filing first</option>
            </Select>
            <Select value={status} onChange={(event) => setStatus(event.target.value)} className="h-8 w-44 text-xs">
              {STATUS_OPTIONS.map((option) => (
                <option key={option} value={option}>
                  {option ? option[0].toUpperCase() + option.slice(1) : "All statuses"}
                </option>
              ))}
            </Select>
            <div className="flex items-center gap-1.5">
              <span className="text-[11px] text-muted-foreground">Expiring before</span>
              <Input
                type="date"
                value={expiringBefore}
                onChange={(event) => setExpiringBefore(event.target.value)}
                className="h-8 w-40 text-xs"
              />
            </div>
            <span className="ml-auto flex items-center gap-1 text-[11px] text-muted-foreground">
              <Info className="h-3 w-3" /> Baseline ingestions never raise alerts — only deltas do.
            </span>
          </>
        }
      />
    </div>
  );
}
