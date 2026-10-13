"use client";

import * as React from "react";
import { useQuery } from "@tanstack/react-query";
import { FlaskConical } from "lucide-react";
import { api } from "@/lib/api";
import { Input } from "@/components/ui/input";
import { DataTable, type Column } from "@/components/tables/data-table";
import { AreaTrend, BarSeries } from "@/components/charts/charts";
import { KpiCard } from "@/components/common/kpi-card";
import { SourceProvenance } from "@/components/common/source-provenance";
import { OfficialSourceBanner } from "@/components/common/official-source-banner";
import { SourceCells } from "@/components/common/source-cells";
import { fmtDate, fmtNumber, rawValue } from "@/lib/format";
import { useDebounced } from "@/hooks/use-debounce";
import type { ActiveMoiety } from "@/types/api";

export default function PdePage() {
  const [page, setPage] = React.useState(1);
  const [search, setSearch] = React.useState("");
  const [sponsor, setSponsor] = React.useState("");
  const debounced = useDebounced(search, 350);
  React.useEffect(() => setPage(1), [debounced, sponsor]);

  const params = { page, page_size: 50, q: debounced || undefined, sponsor: sponsor || undefined };
  const query = useQuery({ queryKey: ["pde-moieties", params], queryFn: () => api.pdeMoieties(params) });
  const summary = useQuery({ queryKey: ["pde-summary"], queryFn: () => api.pdeSummary() });
  const yearly = useQuery({ queryKey: ["pde-yearly"], queryFn: () => api.pdeYearlyTrend(20) });
  const sponsors = useQuery({ queryKey: ["pde-sponsors"], queryFn: () => api.pdeTopSponsors(15) });

  const columns: Column<ActiveMoiety>[] = [
    {
      key: "moiety_name",
      header: "Active moiety",
      render: (row) => (
        <span className="font-medium">{rawValue(row, "Active Moiety", "moiety_name") ?? "—"}</span>
      ),
    },
    {
      key: "sponsor_name",
      header: "Sponsor",
      render: (row) => rawValue(row, "Sponsor", "sponsor_name") ?? "—",
    },
    {
      key: "date_issued",
      header: "Date issued",
      render: (row) => rawValue(row, "Date Issued", "date_issued") ?? fmtDate(row.date_issued),
    },
    {
      key: "approval_year",
      header: "Year",
      align: "right",
      render: (row) => (row.approval_year ? String(row.approval_year) : "—"),
    },
    {
      key: "status",
      header: "Status",
      render: (row) => row.status ?? (row.date_issued ? "Approved" : "—"),
    },
  ];

  return (
    <div className="space-y-5">
      <header>
        <h1 className="flex items-center gap-2 text-xl font-semibold">
          <FlaskConical className="h-5 w-5 text-primary" /> Approved Active Moiety (PDE)
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Written requests issued by FDA identifying the approved active moiety — the basis for new chemical
          entity exclusivity determinations.
        </p>
        <OfficialSourceBanner module="pde" />
        <SourceProvenance module="pde" />
      </header>

      <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {summary.data ? (
          <>
            <KpiCard label="Total moieties" value={summary.data.total_moieties} tone="primary" />
            <KpiCard label="Distinct sponsors" value={summary.data.distinct_sponsors} />
            <KpiCard label="Approved (12 months)" value={summary.data.approved_last_12_months} tone="success" />
          </>
        ) : null}
      </section>

      <section className="grid gap-4 xl:grid-cols-2">
        {yearly.data ? (
          <AreaTrend
            title="Approved active moieties by year"
            subtitle="New moieties recognised per calendar year"
            data={yearly.data as unknown as Array<Record<string, string | number>>}
            xKey="year"
            yKey="count"
            color="hsl(170 70% 45%)"
          />
        ) : null}
        {sponsors.data ? (
          <BarSeries
            title="Top sponsors"
            subtitle="Sponsors by number of approved active moieties"
            data={sponsors.data as unknown as Array<Record<string, string | number>>}
            xKey="sponsor"
            layout="vertical"
            bars={[{ key: "count", label: "Moieties", color: "hsl(20 85% 58%)" }]}
            height={320}
          />
        ) : null}
      </section>

      <DataTable<ActiveMoiety>
        title="Approved active moieties"
        description="Every moiety with its sponsor and issue date"
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
        onSearch={setSearch}
        searchPlaceholder="Search active moiety…"
        exportPath="/pde/export"
        renderDetail={(row) => <SourceCells raw={row.raw} />}
        filters={
          <div className="flex items-center gap-1.5">
            <span className="text-[11px] text-muted-foreground">Sponsor</span>
            <Input
              value={sponsor}
              onChange={(event) => setSponsor(event.target.value)}
              placeholder="Filter by sponsor…"
              className="h-8 w-52 text-xs"
            />
          </div>
        }
      />
    </div>
  );
}
