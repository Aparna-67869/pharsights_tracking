"use client";

import * as React from "react";
import { useQuery } from "@tanstack/react-query";
import { Download, ExternalLink, Eye, FileSpreadsheet, FileText, Package } from "lucide-react";
import { api, getToken } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { SourceViewerModal } from "@/components/common/source-viewer-modal";
import { fmtDate, fmtNumber, fmtRelative } from "@/lib/format";
import { useNow } from "@/hooks/use-now";
import { useRealtime } from "@/components/providers/realtime-provider";
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
 * is built from, exactly when the regulator published it, when the collector
 * fetched and last processed it, plus one-click access to the original document.
 *
 * Download and last-processed stamps are absolute, so their relative form is
 * recomputed on a clock tick rather than being frozen at first render. The
 * panel also reconciles with the live event stream: when a sweep finishes for
 * this module the document query is refetched, so the stamps advance on their
 * own instead of waiting for the stale window to lapse.
 */
export function SourceProvenance({ module }: { module: string }) {
  useNow(30_000);
  const realtime = useRealtime();
  const [viewerOpen, setViewerOpen] = React.useState(false);
  const source = useQuery({
    queryKey: ["module-source", module],
    queryFn: () => api.moduleSource(module),
    staleTime: 60_000,
  });

  const refresh = source.refetch;
  React.useEffect(() => {
    return realtime.subscribe((event) => {
      if (
        event.topic === "pharma.pipeline.run" ||
        event.topic.startsWith(`pharma.${module}`)
      ) {
        void refresh();
      }
    });
  }, [realtime, module, refresh]);

  const data: SourceDocumentMeta | undefined = source.data;

  const scheduler = useQuery({
    queryKey: ["scheduler"],
    queryFn: () => api.schedulerStatus(),
    refetchInterval: 30_000,
  });

  if (!data) return null;

  const Icon = data.document_kind === "xlsx" || data.document_kind === "xls"
    ? FileSpreadsheet
    : data.document_kind === "zip"
      ? Package
      : FileText;

  // A source workbook can list rows the platform legitimately drops (rejected by
  // validation, or an exact duplicate). Surface the gap rather than hide it.
  const dropped =
    data.source_record_count != null && data.record_count != null
      ? Math.max(0, data.source_record_count - data.record_count)
      : 0;

  const fields: Array<{ label: string; value: React.ReactNode }> = [
    { label: "Source file", value: <span className="font-medium text-foreground">{data.filename ?? "—"}</span> },
    {
      label: "Published",
      value: data.publication_date
        ? (data.publication_label ?? fmtDate(data.publication_date))
        : "—",
    },
    { label: "Auto-fetched", value: liveStamp(data.fetched_at) },
    { label: "Last processed", value: liveStamp(data.last_processed_at) },
    { label: "Version", value: `v${data.version ?? 1}` },
    {
      label: "Records",
      value:
        data.record_count != null
          ? dropped > 0
            ? `${fmtNumber(data.record_count)} (of ${fmtNumber(data.source_record_count ?? 0)} source rows)`
            : fmtNumber(data.record_count)
          : "—",
    },
    {
      label: "Next sweep",
      value: scheduler.data?.next_run_at ? liveStamp(scheduler.data.next_run_at) : "—",
    },
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
            onClick={() => setViewerOpen(true)}
            title="Inspect the archived source document"
          >
            <FileText className="h-4 w-4" />
            {data.official_document_label ?? `View Official ${MODULE_TITLES[module] ?? module}`}
          </Button>
          <Button
            variant="outline"
            size="sm"
            className="h-8"
            onClick={() => setViewerOpen(true)}
            title="View the source file inline without downloading"
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
      <dl className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 border-t border-border/60 pt-2 text-[11px] sm:grid-cols-3 lg:grid-cols-7">
        {fields.map((field) => (
          <div key={field.label} className="min-w-0">
            <dt className="truncate text-muted-foreground">{field.label}</dt>
            <dd className="min-w-0">{field.value}</dd>
          </div>
        ))}
      </dl>
      <SourceViewerModal
        module={module}
        open={viewerOpen}
        onClose={() => setViewerOpen(false)}
        title={`${data.source_name ?? MODULE_TITLES[module] ?? module} — source file`}
      />
    </div>
  );
}

/**
 * Render a timestamp as "12 Oct 2026, 10:50 · 6 minutes ago". The relative half
 * is recomputed on each clock tick (see ``useNow``) so the label stays truthful
 * without a reload, which is what an operator reads to judge whether monitoring
 * is alive.
 */
function liveStamp(value?: string | null): React.ReactNode {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  const absolute = date.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
  return (
    <span title={date.toISOString()} className="inline-flex flex-wrap items-center gap-1">
      <span>{absolute}</span>
      <span className="text-muted-foreground">· {fmtRelative(value)}</span>
    </span>
  );
}
