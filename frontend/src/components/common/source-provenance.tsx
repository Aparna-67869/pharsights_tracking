"use client";

import * as React from "react";
import { useQuery } from "@tanstack/react-query";
import { Download, ExternalLink, Eye, FileSpreadsheet, FileText, Package } from "lucide-react";
import { api, getToken } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { fmtDate, fmtNumber } from "@/lib/format";
import type { SourceDocumentMeta } from "@/types/api";

const MODULE_TITLES: Record<string, string> = {
  ftf: "FDA Paragraph IV Certifications List",
  pte: "USPTO Patent Term Extension register",
  pde: "FDA Approved Active Moieties",
  orange_book: "FDA Orange Book data files",
};

function formatBytes(bytes?: number | null): string | null {
  if (!bytes) return null;
  const units = ["B", "KB", "MB", "GB"];
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value.toFixed(value >= 10 || unit === 0 ? 0 : 1)} ${units[unit]}`;
}

function openWithToken(url: string, download = false) {
  const token = getToken();
  const headers: Record<string, string> = token ? { Authorization: `Bearer ${token}` } : {};
  void fetch(url, { headers })
    .then((response) => response.blob())
    .then((blob) => {
      const href = URL.createObjectURL(blob);
      if (download) {
        const anchor = document.createElement("a");
        anchor.href = href;
        anchor.download = "";
        anchor.click();
      } else {
        window.open(href, "_blank", "noopener,noreferrer");
      }
      setTimeout(() => URL.revokeObjectURL(href), 60_000);
    });
}

/**
 * Provenance bar shown under every module header: which official file the page
 * is built from, exactly when the regulator published it, when we downloaded
 * and last processed it, plus one-click access to the original document.
 */
export function SourceProvenance({ module }: { module: string }) {
  const source = useQuery({
    queryKey: ["module-source", module],
    queryFn: () => api.moduleSource(module),
    staleTime: 60_000,
  });

  const data: SourceDocumentMeta | undefined = source.data;
  if (!data) return null;

  const Icon = data.document_kind === "xlsx" || data.document_kind === "xls"
    ? FileSpreadsheet
    : data.document_kind === "zip"
      ? Package
      : FileText;

  const fields: Array<{ label: string; value: React.ReactNode }> = [
    { label: "Source file", value: <span className="font-medium text-foreground">{data.filename ?? "—"}</span> },
    {
      label: "Published",
      value: data.publication_date
        ? (data.publication_label ?? fmtDate(data.publication_date))
        : "—",
    },
    { label: "Downloaded", value: fmtDateTime(data.fetched_at) },
    { label: "Last processed", value: fmtDateTime(data.last_processed_at) },
    { label: "Version", value: `v${data.version ?? 1}` },
    { label: "Records", value: data.record_count != null ? fmtNumber(data.record_count) : "—" },
  ];

  return (
    <div className="mt-3 rounded-xl border border-border/70 bg-muted/25 px-3 py-2.5 text-xs">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <span className="inline-flex items-center gap-1.5 font-medium">
          <Icon className="h-3.5 w-3.5 text-primary" />
          {data.source_name ?? MODULE_TITLES[module] ?? module}
        </span>
        <span className="hidden text-muted-foreground sm:inline">·</span>
        <span className="text-muted-foreground">
          {formatBytes(data.byte_size) ?? "official source"} ·{" "}
          {data.storage_backend === "azure_blob" ? "Azure Blob" : "platform archive"}
        </span>
        <span className="ml-auto flex flex-wrap items-center gap-2">
          <Button
            size="sm"
            className="h-8 bg-primary font-medium text-primary-foreground shadow-glow hover:bg-primary/90"
            onClick={() => openWithToken(api.officialDocumentUrl(module, "view"))}
            title="Open the official regulator document (archived copy)"
          >
            <FileText className="h-4 w-4" />
            {data.official_document_label ?? `View Official ${MODULE_TITLES[module] ?? module}`}
          </Button>
          <Button
            variant="outline"
            size="sm"
            className="h-8"
            onClick={() => openWithToken(api.sourceFileUrl(module, "view"))}
          >
            <Eye className="h-3.5 w-3.5" /> View source
          </Button>
          <Button
            variant="outline"
            size="sm"
            className="h-8"
            onClick={() => openWithToken(api.sourceFileUrl(module, "download"), true)}
          >
            <Download className="h-3.5 w-3.5" /> Download
          </Button>
          {data.official_site_url ? (
            <a
              href={data.official_site_url}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1 text-primary underline-offset-2 hover:underline"
            >
              <ExternalLink className="h-3 w-3" /> Regulator page
            </a>
          ) : null}
        </span>
      </div>
      <dl className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 border-t border-border/60 pt-2 text-[11px] sm:grid-cols-3 lg:grid-cols-6">
        {fields.map((field) => (
          <div key={field.label} className="min-w-0">
            <dt className="truncate text-muted-foreground">{field.label}</dt>
            <dd className="truncate">{field.value}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

function fmtDateTime(value?: string | null): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}
