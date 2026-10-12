"use client";

import * as React from "react";
import { useQuery } from "@tanstack/react-query";
import { Database, Download, GitCompareArrows, History, Info } from "lucide-react";
import { API_BASE, api, getToken } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Select } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { DataTable, type Column } from "@/components/tables/data-table";
import { KpiCard } from "@/components/common/kpi-card";
import { fmtDate, fmtDateTime, fmtNumber } from "@/lib/format";
import { useDebounced } from "@/hooks/use-debounce";
import type { OrangeBookPatent, OrangeBookProduct, OrangeBookSupplement } from "@/types/api";

export default function OrangeBookPage() {
  const [tab, setTab] = React.useState("products");
  const summary = useQuery({ queryKey: ["ob-summary"], queryFn: () => api.obSummary() });

  return (
    <div className="space-y-5">
      <header>
        <h1 className="flex items-center gap-2 text-xl font-semibold">
          <Database className="h-5 w-5 text-primary" /> Orange Book
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Approved drug products with therapeutic equivalence evaluations, patent listings and exclusivity
          grants — plus monthly supplement version comparison.
        </p>
      </header>

      <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {summary.data ? (
          <>
            <KpiCard label="Active products" value={summary.data.total_products} hint={`${fmtNumber(summary.data.nda_products)} NDA · ${fmtNumber(summary.data.anda_products)} ANDA`} tone="primary" />
            <KpiCard label="Patent listings" value={summary.data.patent_listings} />
            <KpiCard label="Exclusivity grants" value={summary.data.exclusivity_grants} tone="success" />
            <KpiCard
              label="Current supplement"
              value={summary.data.current_supplement?.edition ?? summary.data.current_supplement?.number ?? "—"}
              hint={
                summary.data.current_supplement?.publication_month
                  ? `${summary.data.current_supplement.publication_month}/${summary.data.current_supplement.publication_year}`
                  : undefined
              }
              tone="warning"
            />
          </>
        ) : null}
      </section>

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList>
          <TabsTrigger value="products">
            <Database className="h-3.5 w-3.5" /> Products
          </TabsTrigger>
          <TabsTrigger value="patents">
            <GitCompareArrows className="h-3.5 w-3.5" /> Patent listings
          </TabsTrigger>
          <TabsTrigger value="supplements">
            <History className="h-3.5 w-3.5" /> Supplements
          </TabsTrigger>
          <TabsTrigger value="documents">
            <Download className="h-3.5 w-3.5" /> Documents
          </TabsTrigger>
        </TabsList>
        <TabsContent value="products" className="mt-4">
          <ProductsTable />
        </TabsContent>
        <TabsContent value="patents" className="mt-4">
          <PatentsTable />
        </TabsContent>
        <TabsContent value="supplements" className="mt-4">
          <SupplementsPanel />
        </TabsContent>
        <TabsContent value="documents" className="mt-4">
          <DocumentsPanel />
        </TabsContent>
      </Tabs>
    </div>
  );
}

function ProductsTable() {
  const [page, setPage] = React.useState(1);
  const [search, setSearch] = React.useState("");
  const [applType, setApplType] = React.useState("");
  const [teCode, setTeCode] = React.useState("");
  const debounced = useDebounced(search, 350);
  React.useEffect(() => setPage(1), [debounced, applType, teCode]);

  const params = {
    page,
    page_size: 50,
    q: debounced || undefined,
    appl_type: applType || undefined,
    te_code: teCode || undefined,
  };
  const query = useQuery({ queryKey: ["ob-products", params], queryFn: () => api.obProducts(params) });

  const columns: Column<OrangeBookProduct>[] = [
    {
      key: "trade_name",
      header: "Product",
      render: (row) => (
        <div>
          <p className="font-medium">{row.trade_name ?? "—"}</p>
          <p className="text-[11px] text-muted-foreground">{row.ingredient ?? "—"}</p>
        </div>
      ),
    },
    {
      key: "application",
      header: "Application",
      render: (row) => (
        <span className="font-mono text-xs">
          {row.appl_type}
          {row.appl_no}
        </span>
      ),
    },
    { key: "applicant_full_name", header: "Applicant", render: (row) => row.applicant_full_name ?? row.applicant ?? "—" },
    { key: "strength", header: "Strength", render: (row) => row.strength ?? "—" },
    { key: "dosage_form_route", header: "Form / route", render: (row) => row.dosage_form_route ?? "—" },
    {
      key: "te_code",
      header: "TE code",
      render: (row) => (row.te_code ? <Badge variant="secondary">{row.te_code}</Badge> : "—"),
    },
    {
      key: "rld",
      header: "RLD / RS",
      render: (row) => (
        <div className="flex gap-1">
          {row.rld ? <Badge variant="success">RLD</Badge> : null}
          {row.rs ? <Badge variant="warning">RS</Badge> : null}
          {!row.rld && !row.rs ? <span className="text-muted-foreground">—</span> : null}
        </div>
      ),
    },
    { key: "approval_date", header: "Approved", render: (row) => fmtDate(row.approval_date) },
  ];

  return (
    <DataTable<OrangeBookProduct>
      title="Orange Book products"
      description="Approved drug products with therapeutic equivalence evaluations"
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
      searchPlaceholder="Search trade name or ingredient…"
      exportPath="/orange-book/export/products"
      exportParams={{ appl_type: applType || undefined }}
      filters={
        <>
          <Select value={applType} onChange={(event) => setApplType(event.target.value)} className="h-8 w-36 text-xs">
            <option value="">NDA &amp; ANDA</option>
            <option value="N">NDA only</option>
            <option value="A">ANDA only</option>
          </Select>
          <Select value={teCode} onChange={(event) => setTeCode(event.target.value)} className="h-8 w-36 text-xs">
            <option value="">All TE codes</option>
            {["AB", "AA", "AN", "AO", "AP", "AT", "BC", "BD", "BE", "BN", "BP", "BS", "BT", "BX"].map((code) => (
              <option key={code} value={code}>
                {code}
              </option>
            ))}
          </Select>
        </>
      }
    />
  );
}

function PatentsTable() {
  const [page, setPage] = React.useState(1);
  const [search, setSearch] = React.useState("");
  const debounced = useDebounced(search, 350);
  React.useEffect(() => setPage(1), [debounced]);

  const params = { page, page_size: 50, q: debounced || undefined };
  const query = useQuery({ queryKey: ["ob-patents", params], queryFn: () => api.obPatents(params) });

  const columns: Column<OrangeBookPatent>[] = [
    { key: "patent_number", header: "Patent", render: (row) => <span className="font-mono text-xs">{row.patent_number}</span> },
    {
      key: "application",
      header: "Application",
      render: (row) => (
        <span className="font-mono text-xs">
          {row.appl_type}
          {row.appl_no}
        </span>
      ),
    },
    { key: "expiration_date", header: "Expiration", render: (row) => fmtDate(row.expiration_date) },
    {
      key: "drug_substance_flag",
      header: "Substance",
      render: (row) => (row.drug_substance_flag ? <Badge variant="success">Yes</Badge> : "—"),
    },
    {
      key: "drug_product_flag",
      header: "Product",
      render: (row) => (row.drug_product_flag ? <Badge variant="success">Yes</Badge> : "—"),
    },
    { key: "patent_use_code", header: "Use code", render: (row) => row.patent_use_code ?? "—" },
    {
      key: "delist_flag",
      header: "Delisted",
      render: (row) => (row.delist_flag ? <Badge variant="destructive">Yes</Badge> : "—"),
    },
  ];

  return (
    <DataTable<OrangeBookPatent>
      title="Orange Book patent listings"
      description="Patents listed against approved products, with delisting flags"
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
      searchPlaceholder="Search patent or application…"
    />
  );
}

function SupplementsPanel() {
  const supplements = useQuery({ queryKey: ["ob-supplements"], queryFn: () => api.obSupplements(36) });
  const compare = useQuery({ queryKey: ["ob-compare"], queryFn: () => api.obCompare() });

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="flex-row items-center justify-between">
          <div>
            <CardTitle className="flex items-center gap-2">
              <GitCompareArrows className="h-4 w-4 text-primary" /> Latest supplement comparison
            </CardTitle>
            <p className="mt-0.5 text-xs text-muted-foreground">
              Automatic diff between the two most recent Orange Book cumulative supplements
            </p>
          </div>
        </CardHeader>
        <CardContent>
          {compare.isLoading ? (
            <div className="h-24 animate-pulse rounded-lg bg-muted/50" />
          ) : compare.data ? (
            <pre className="scrollbar-thin max-h-72 overflow-auto rounded-lg border border-border/70 bg-surface-muted/40 p-3 text-[11px]">
              {JSON.stringify(compare.data, null, 2)}
            </pre>
          ) : (
            <p className="py-6 text-center text-xs text-muted-foreground">
              Only one supplement edition has been archived so far. The comparison appears once a second
              edition is published.
            </p>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Supplement edition history</CardTitle>
          <p className="mt-0.5 text-xs text-muted-foreground">
            Monthly cumulative supplements with added, removed and modified product counts
          </p>
        </CardHeader>
        <CardContent className="p-0">
          <div className="scrollbar-thin max-h-[48vh] overflow-auto">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Supplement</th>
                  <th>Edition</th>
                  <th>Published</th>
                  <th className="text-right">Added</th>
                  <th className="text-right">Removed</th>
                  <th className="text-right">Modified</th>
                  <th>Current</th>
                </tr>
              </thead>
              <tbody>
                {(supplements.data ?? []).map((row: OrangeBookSupplement) => (
                  <tr key={row.id}>
                    <td className="font-mono text-xs">{row.supplement_number}</td>
                    <td>{row.edition ?? "—"}</td>
                    <td>{fmtDate(row.publication_date) !== "—" ? fmtDate(row.publication_date) : `${row.publication_month ?? ""}/${row.publication_year ?? ""}`}</td>
                    <td className="text-right tabular-nums">{fmtNumber(row.products_added ?? 0)}</td>
                    <td className="text-right tabular-nums">{fmtNumber(row.products_removed ?? 0)}</td>
                    <td className="text-right tabular-nums">{fmtNumber(row.products_modified ?? 0)}</td>
                    <td>{row.is_current ? <Badge variant="success">Current</Badge> : "—"}</td>
                  </tr>
                ))}
                {(supplements.data ?? []).length === 0 ? (
                  <tr>
                    <td colSpan={7} className="py-8 text-center text-xs text-muted-foreground">
                      No supplements archived yet.
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

function DocumentsPanel() {
  const documents = useQuery({ queryKey: ["ob-documents"], queryFn: () => api.obDocuments() });

  const download = (id: string, filename: string) => {
    const token = getToken();
    void fetch(`${API_BASE}/api/v1/orange-book/documents/${id}/download`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    })
      .then((response) => response.blob())
      .then((blob) => {
        const href = URL.createObjectURL(blob);
        const anchor = document.createElement("a");
        anchor.href = href;
        anchor.download = filename;
        anchor.click();
        URL.revokeObjectURL(href);
      });
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Archived source documents</CardTitle>
        <p className="mt-0.5 text-xs text-muted-foreground">
          Every Orange Book artifact the platform has downloaded, retained for audit and offline access
        </p>
      </CardHeader>
      <CardContent className="p-0">
        <div className="scrollbar-thin max-h-[56vh] overflow-auto">
          <table className="data-table">
            <thead>
              <tr>
                <th>Filename</th>
                <th>Source</th>
                <th>Version</th>
                <th>Fetched</th>
                <th className="text-right">Size</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {(documents.data ?? []).map((doc) => (
                <tr key={doc.id}>
                  <td className="max-w-[280px] truncate">{doc.filename}</td>
                  <td className="font-mono text-xs">{doc.source_code}</td>
                  <td>
                    {doc.version ? <Badge variant="secondary">{doc.version}</Badge> : "—"}
                    {doc.is_current ? <Badge variant="success" className="ml-1">current</Badge> : null}
                  </td>
                  <td>{fmtDateTime(doc.fetched_at)}</td>
                  <td className="text-right tabular-nums">{doc.byte_size ? `${(doc.byte_size / 1024).toFixed(0)} KB` : "—"}</td>
                  <td className="text-right">
                    <Button variant="outline" size="sm" onClick={() => download(doc.id, doc.filename)}>
                      <Download className="h-3.5 w-3.5" /> Download
                    </Button>
                  </td>
                </tr>
              ))}
              {(documents.data ?? []).length === 0 ? (
                <tr>
                  <td colSpan={6} className="py-8 text-center text-xs text-muted-foreground">
                    No documents archived yet.
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </CardContent>
      <div className="flex items-center gap-1 border-t border-border/70 px-4 py-2 text-[11px] text-muted-foreground">
        <Info className="h-3 w-3" /> Documents are stored in the platform artifact store and served through the
        authenticated API.
      </div>
    </Card>
  );
}
