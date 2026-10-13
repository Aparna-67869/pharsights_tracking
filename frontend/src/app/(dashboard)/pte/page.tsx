"use client";

import * as React from "react";
import { useQuery } from "@tanstack/react-query";
import { CalendarClock, FileText, ScrollText } from "lucide-react";
import { api } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Input, Select } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { DataTable, type Column } from "@/components/tables/data-table";
import { AreaTrend, BarSeries } from "@/components/charts/charts";
import { KpiCard } from "@/components/common/kpi-card";
import { SourceProvenance } from "@/components/common/source-provenance";
import { OfficialSourceBanner } from "@/components/common/official-source-banner";
import { SourceCells } from "@/components/common/source-cells";
import { fmtDate, fmtExtension, fmtNumber, rawValue } from "@/lib/format";
import { useDebounced } from "@/hooks/use-debounce";
import type { PteApplication, PteCertificate } from "@/types/api";

export default function PtePage() {
  const [tab, setTab] = React.useState("applications");

  return (
    <div className="space-y-5">
      <header>
        <h1 className="flex items-center gap-2 text-xl font-semibold">
          <CalendarClock className="h-5 w-5 text-primary" /> Patent Term Extension (USPTO)
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Applications under 35 U.S.C. §156 and the certificates granting extended term, monitored from the
          USPTO register.
        </p>
        <OfficialSourceBanner module="pte" />
        <SourceProvenance module="pte" />
      </header>

      <PteSummary />

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList>
          <TabsTrigger value="applications">
            <FileText className="h-3.5 w-3.5" /> Applications
          </TabsTrigger>
          <TabsTrigger value="certificates">
            <ScrollText className="h-3.5 w-3.5" /> Certificates
          </TabsTrigger>
          <TabsTrigger value="analytics">
            <CalendarClock className="h-3.5 w-3.5" /> Analytics
          </TabsTrigger>
        </TabsList>
        <TabsContent value="applications" className="mt-4">
          <ApplicationsTable />
        </TabsContent>
        <TabsContent value="certificates" className="mt-4">
          <CertificatesTable />
        </TabsContent>
        <TabsContent value="analytics" className="mt-4">
          <Analytics />
        </TabsContent>
      </Tabs>
    </div>
  );
}

function PteSummary() {
  const { data } = useQuery({ queryKey: ["pte-summary"], queryFn: () => api.pteSummary() });
  if (!data) return null;
  return (
    <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
      <KpiCard label="Applications" value={data.applications_total} tone="primary" />
      <KpiCard label="Certificates granted" value={data.certificates_total} tone="success" />
      <KpiCard
        label="Average extension"
        value={data.average_extension_days != null ? `${Math.round(data.average_extension_days)} d` : "—"}
      />
      <KpiCard
        label="New in last 12m"
        value={data.applications_last_12_months}
        hint={`${fmtNumber(data.certificates_last_12_months)} certificates granted in the period`}
        tone="warning"
      />
    </section>
  );
}

function ApplicationsTable() {
  const [page, setPage] = React.useState(1);
  const [search, setSearch] = React.useState("");
  const [filedFrom, setFiledFrom] = React.useState("");
  const debounced = useDebounced(search, 350);
  React.useEffect(() => setPage(1), [debounced, filedFrom]);

  const params = { page, page_size: 50, q: debounced || undefined, filed_from: filedFrom || undefined };
  const query = useQuery({ queryKey: ["pte-applications", params], queryFn: () => api.pteApplications(params) });

  const columns: Column<PteApplication>[] = [
    {
      key: "patent_number",
      header: "Patent",
      render: (row) => (
        <span className="font-mono text-xs">
          {rawValue(row, "U.S. Patent No", "patent_number") ?? "—"}
        </span>
      ),
    },
    {
      key: "trade_name",
      header: "Product",
      render: (row) => (
        <div>
          <p className="font-medium">{rawValue(row, "Product", "trade_name") ?? "—"}</p>
          {rawValue(row, "Generic Name", "generic_name") ? (
            <p className="text-[11px] text-muted-foreground">
              {rawValue(row, "Generic Name", "generic_name")}
            </p>
          ) : null}
        </div>
      ),
    },
    {
      key: "application_number",
      header: "Application",
      render: (row) => (
        <span className="font-mono text-xs">
          {rawValue(row, "U.S. Application No", "application_number") ?? "—"}
        </span>
      ),
    },
    { key: "sponsor_name", header: "Sponsor", render: (row) => rawValue(row, "Sponsor", "sponsor_name") ?? "—" },
    { key: "filing_date", header: "Filed", render: (row) => fmtDate(row.filing_date) },
    {
      key: "status",
      header: "Status",
      render: (row) => (row.status ? <Badge variant="secondary">{row.status}</Badge> : "—"),
    },
  ];

  return (
    <DataTable<PteApplication>
      title="PTE applications"
      description="Patent term extension applications filed with the USPTO"
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
      searchPlaceholder="Search patent, trade or generic name…"
      exportPath="/pte/export/applications"
      renderDetail={(row) => <SourceCells raw={row.raw} />}
      filters={
        <div className="flex items-center gap-1.5">
          <span className="text-[11px] text-muted-foreground">Filed from</span>
          <Input type="date" value={filedFrom} onChange={(event) => setFiledFrom(event.target.value)} className="h-8 w-40 text-xs" />
        </div>
      }
    />
  );
}

function CertificatesTable() {
  const [page, setPage] = React.useState(1);
  const [search, setSearch] = React.useState("");
  const [minDays, setMinDays] = React.useState("");
  const debounced = useDebounced(search, 350);
  React.useEffect(() => setPage(1), [debounced, minDays]);

  const params = {
    page,
    page_size: 50,
    q: debounced || undefined,
    min_extension_days: minDays ? Number(minDays) : undefined,
  };
  const query = useQuery({ queryKey: ["pte-certificates", params], queryFn: () => api.pteCertificates(params) });

  const columns: Column<PteCertificate>[] = [
    {
      key: "patent_number",
      header: "Patent",
      render: (row) => (
        <span className="font-mono text-xs">
          {rawValue(row, "Patent No", "patent_number") ?? "—"}
        </span>
      ),
    },
    {
      key: "trade_name",
      header: "Product",
      render: (row) => (
        <div>
          <p className="font-medium">{rawValue(row, "Product", "trade_name") ?? "—"}</p>
          {rawValue(row, "Generic Name", "generic_name") ? (
            <p className="text-[11px] text-muted-foreground">
              {rawValue(row, "Generic Name", "generic_name")}
            </p>
          ) : null}
        </div>
      ),
    },
    { key: "sponsor_name", header: "Sponsor", render: (row) => rawValue(row, "Sponsor", "sponsor_name") ?? "—" },
    { key: "original_expiration_date", header: "Original expiry", render: (row) => fmtDate(row.original_expiration_date) },
    { key: "extended_expiration_date", header: "Extended expiry", render: (row) => fmtDate(row.extended_expiration_date) },
    {
      key: "extension_days",
      header: "Extension",
      align: "right",
      render: (row) => <span className="font-medium">{fmtExtension(row.extension_days)}</span>,
    },
    { key: "granted_date", header: "Granted", render: (row) => fmtDate(row.granted_date) },
  ];

  return (
    <DataTable<PteCertificate>
      title="PTE certificates"
      description="Granted extensions, sorted by longest extension first"
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
      searchPlaceholder="Search patent, trade or generic name…"
      exportPath="/pte/export/certificates"
      renderDetail={(row) => <SourceCells raw={row.raw} />}
      filters={
        <div className="flex items-center gap-1.5">
          <span className="text-[11px] text-muted-foreground">Min extension (days)</span>
          <Input
            type="number"
            min={0}
            value={minDays}
            onChange={(event) => setMinDays(event.target.value)}
            placeholder="e.g. 1825"
            className="h-8 w-32 text-xs"
          />
        </div>
      }
    />
  );
}

function Analytics() {
  const trend = useQuery({ queryKey: ["pte-trend"], queryFn: () => api.pteMonthlyTrend(60) });
  const distribution = useQuery({
    queryKey: ["pte-distribution"],
    queryFn: () => api.pteExtensionDistribution(),
  });

  return (
    <div className="grid gap-4 xl:grid-cols-2">
      {trend.data ? (
        <AreaTrend
          title="Monthly PTE application trend"
          subtitle="Applications filed per month (60 months)"
          data={trend.data}
          xKey="month"
          yKey="count"
          color="hsl(280 65% 62%)"
        />
      ) : null}
      {distribution.data ? (
        <BarSeries
          title="Granted extension length distribution"
          subtitle="Certificates grouped by extension length"
          data={distribution.data as unknown as Array<Record<string, string | number>>}
          xKey="band"
          bars={[{ key: "count", label: "Certificates", color: "hsl(142 69% 50%)" }]}
        />
      ) : null}
    </div>
  );
}
