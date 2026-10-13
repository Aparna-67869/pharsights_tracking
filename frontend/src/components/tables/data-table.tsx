"use client";

import * as React from "react";
import { ChevronDown, ChevronLeft, ChevronRight, Download, FileSpreadsheet, Filter, RotateCw, X } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import { fmtNumber } from "@/lib/format";
import { api, getToken } from "@/lib/api";

export interface Column<T> {
  key: string;
  header: string;
  render?: (row: T) => React.ReactNode;
  className?: string;
  sortable?: boolean;
  align?: "left" | "right";
}

export function DataTable<T extends { id?: string }>({
  title,
  description,
  columns,
  rows,
  total,
  page,
  pageSize,
  pages,
  loading,
  error,
  onPageChange,
  onRefresh,
  onSearch,
  searchPlaceholder,
  filters,
  exportPath,
  exportParams,
  emptyMessage = "No records found",
  toolbar,
  renderDetail,
}: {
  title: string;
  description?: string;
  columns: Column<T>[];
  rows: T[];
  total: number;
  page: number;
  pageSize: number;
  pages: number;
  loading?: boolean;
  error?: string | null;
  onPageChange: (page: number) => void;
  onRefresh?: () => void;
  onSearch?: (value: string) => void;
  searchPlaceholder?: string;
  filters?: React.ReactNode;
  exportPath?: string;
  exportParams?: Record<string, unknown>;
  emptyMessage?: string;
  toolbar?: React.ReactNode;
  renderDetail?: (row: T) => React.ReactNode;
}) {
  const [query, setQuery] = React.useState("");
  const [expanded, setExpanded] = React.useState<string | null>(null);
  const [exportOpen, setExportOpen] = React.useState(false);

  const download = (format: "csv" | "xlsx" = "csv") => {
    if (!exportPath) return;
    const url = api.exportUrl(exportPath, { ...exportParams, format });
    const token = getToken();
    // The export endpoint is bearer-protected; fetch then save as a blob.
    void fetch(url, { headers: token ? { Authorization: `Bearer ${token}` } : {} })
      .then((response) => response.blob())
      .then((blob) => {
        const href = URL.createObjectURL(blob);
        const anchor = document.createElement("a");
        anchor.href = href;
        anchor.download = exportFilename(title, format);
        anchor.click();
        URL.revokeObjectURL(href);
      });
  };

  const start = total === 0 ? 0 : (page - 1) * pageSize + 1;
  const end = Math.min(page * pageSize, total);

  return (
    <Card className="overflow-hidden">
      <div className="flex flex-col gap-3 border-b border-border/70 p-4 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <h2 className="text-sm font-semibold">{title}</h2>
          {description ? <p className="text-xs text-muted-foreground">{description}</p> : null}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {onSearch ? (
            <div className="relative">
              <Input
                value={query}
                onChange={(event) => {
                  setQuery(event.target.value);
                  onSearch(event.target.value);
                }}
                placeholder={searchPlaceholder ?? "Search…"}
                className="w-56 pr-7"
              />
              {query ? (
                <button
                  onClick={() => {
                    setQuery("");
                    onSearch("");
                  }}
                  className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                >
                  <X className="h-3.5 w-3.5" />
                </button>
              ) : null}
            </div>
          ) : null}
          {toolbar}
          {onRefresh ? (
            <Button variant="outline" size="sm" onClick={onRefresh}>
              <RotateCw className={cn("h-3.5 w-3.5", loading && "animate-spin")} />
              Refresh
            </Button>
          ) : null}
          {exportPath ? (
            <div className="relative">
              <Button variant="outline" size="sm" onClick={() => setExportOpen((v) => !v)}>
                <Download className="h-3.5 w-3.5" />
                Export
                <ChevronDown className="h-3.5 w-3.5" />
              </Button>
              {exportOpen ? (
                <>
                  <button
                    className="fixed inset-0 z-10 cursor-default"
                    aria-hidden
                    tabIndex={-1}
                    onClick={() => setExportOpen(false)}
                  />
                  <div className="absolute right-0 z-20 mt-1 w-44 overflow-hidden rounded-lg border border-border bg-card shadow-glass">
                    <button
                      className="flex w-full items-center gap-2 px-3 py-2 text-left text-xs hover:bg-muted/60"
                      onClick={() => {
                        setExportOpen(false);
                        download("csv");
                      }}
                    >
                      <FileSpreadsheet className="h-3.5 w-3.5 text-muted-foreground" /> CSV download
                    </button>
                    <button
                      className="flex w-full items-center gap-2 px-3 py-2 text-left text-xs hover:bg-muted/60"
                      onClick={() => {
                        setExportOpen(false);
                        download("xlsx");
                      }}
                    >
                      <FileSpreadsheet className="h-3.5 w-3.5 text-success" /> Excel (.xlsx)
                    </button>
                  </div>
                </>
              ) : null}
            </div>
          ) : null}
        </div>
      </div>

      {filters ? (
        <div className="flex flex-wrap items-center gap-2 border-b border-border/70 bg-surface-muted/40 px-4 py-2.5">
          <Filter className="h-3.5 w-3.5 text-muted-foreground" />
          {filters}
        </div>
      ) : null}

      <div className="scrollbar-thin max-h-[62vh] overflow-auto">
        <table className="data-table">
          <thead>
            <tr>
              {renderDetail ? <th className="w-8" aria-label="Expand row" /> : null}
              {columns.map((column) => (
                <th
                  key={column.key}
                  className={cn(column.align === "right" && "text-right", column.className)}
                >
                  {column.header}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {loading && rows.length === 0 ? (
              Array.from({ length: 8 }).map((_, index) => (
                <tr key={`skeleton-${index}`}>
                  {renderDetail ? <td /> : null}
                  {columns.map((column) => (
                    <td key={column.key}>
                      <div className="h-4 w-full animate-pulse rounded bg-muted/60" />
                    </td>
                  ))}
                </tr>
              ))
            ) : error ? (
              <tr>
                <td colSpan={columns.length + (renderDetail ? 1 : 0)} className="py-10 text-center text-xs text-destructive">
                  {error}
                </td>
              </tr>
            ) : rows.length === 0 ? (
              <tr>
                <td colSpan={columns.length + (renderDetail ? 1 : 0)} className="py-10 text-center text-xs text-muted-foreground">
                  {emptyMessage}
                </td>
              </tr>
            ) : (
              rows.map((row, index) => {
                const rowId = row.id ?? String(index);
                const isOpen = expanded === rowId;
                return (
                  <React.Fragment key={rowId}>
                    <tr
                      className={cn(renderDetail && "cursor-pointer")}
                      onClick={
                        renderDetail
                          ? () => setExpanded((current) => (current === rowId ? null : rowId))
                          : undefined
                      }
                    >
                      {renderDetail ? (
                        <td className="text-muted-foreground">
                          <ChevronRight className={cn("h-3.5 w-3.5 transition-transform", isOpen && "rotate-90")} />
                        </td>
                      ) : null}
                      {columns.map((column) => (
                        <td
                          key={column.key}
                          className={cn(column.align === "right" && "text-right tabular-nums", column.className)}
                        >
                          {column.render
                            ? column.render(row)
                            : ((row as Record<string, unknown>)[column.key] as React.ReactNode) ?? "—"}
                        </td>
                      ))}
                    </tr>
                    {renderDetail && isOpen ? (
                      <tr className="bg-surface-muted/40">
                        <td />
                        <td colSpan={columns.length} className="px-3 py-3">
                          {renderDetail(row)}
                        </td>
                      </tr>
                    ) : null}
                  </React.Fragment>
                );
              })
            )}
          </tbody>
        </table>
      </div>

      <div className="flex items-center justify-between gap-3 border-t border-border/70 px-4 py-3 text-xs text-muted-foreground">
        <span>
          {fmtNumber(start)}–{fmtNumber(end)} of <Badge variant="secondary">{fmtNumber(total)}</Badge>
        </span>
        <div className="flex items-center gap-1">
          <Button
            variant="outline"
            size="sm"
            disabled={page <= 1}
            onClick={() => onPageChange(page - 1)}
          >
            <ChevronLeft className="h-3.5 w-3.5" />
            Prev
          </Button>
          <span className="px-2 tabular-nums">
            {page} / {Math.max(pages, 1)}
          </span>
          <Button
            variant="outline"
            size="sm"
            disabled={page >= pages}
            onClick={() => onPageChange(page + 1)}
          >
            Next
            <ChevronRight className="h-3.5 w-3.5" />
          </Button>
        </div>
      </div>
    </Card>
  );
}

function exportFilename(title: string, format: string): string {
  return `${title.toLowerCase().replace(/\s+/g, "-")}.${format}`;
}
