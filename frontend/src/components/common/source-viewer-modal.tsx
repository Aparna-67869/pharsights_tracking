"use client";

import * as React from "react";
import { useQuery } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";
import { AlertTriangle, Download, ExternalLink, Loader2, X } from "lucide-react";
import { api, getToken } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { fmtNumber } from "@/lib/format";

/**
 * Inline source-document viewer.
 *
 * "View" must never download. Excel/CSV artifacts are rendered as a real
 * table straight from the stored file; PDFs and archives cannot be tabulated,
 * so the modal offers to open or download them instead of faking a preview.
 */
export function SourceViewerModal({
  module,
  title,
  open,
  onClose,
}: {
  module: string;
  title?: string;
  open: boolean;
  onClose: () => void;
}) {
  const content = useQuery({
    queryKey: ["module-document-content", module],
    queryFn: () => api.moduleDocumentContent(module),
    enabled: open,
    staleTime: 60_000,
  });

  const data = content.data;
  const isPdf = data?.document_kind === "pdf";
  const [pdfUrl, setPdfUrl] = React.useState<string | null>(null);

  // PDFs cannot be tabulated; fetch the artifact and render it inline so "View"
  // still shows the document instead of triggering a download.
  React.useEffect(() => {
    if (!open || !isPdf) {
      setPdfUrl(null);
      return;
    }
    let revoked: string | null = null;
    let cancelled = false;
    void fetchAuthedBlob(api.sourceFileUrl(module, "view")).then((url) => {
      if (cancelled) {
        URL.revokeObjectURL(url);
        return;
      }
      revoked = url;
      setPdfUrl(url);
    });
    return () => {
      cancelled = true;
      if (revoked) URL.revokeObjectURL(revoked);
    };
  }, [open, isPdf, module]);

  React.useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => event.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  return (
    <AnimatePresence>
      {open ? (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="fixed inset-0 z-[70] flex items-start justify-center bg-background/75 p-3 pt-[6vh] backdrop-blur-sm sm:p-6"
        >
          <div className="absolute inset-0" onClick={onClose} />
          <motion.div
            initial={{ opacity: 0, y: 12, scale: 0.99 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 8 }}
            transition={{ duration: 0.16 }}
            className="glass-strong relative z-10 flex max-h-[88vh] w-full max-w-6xl flex-col overflow-hidden rounded-2xl"
          >
            <header className="flex items-center gap-3 border-b border-border/70 px-4 py-3">
              <div className="min-w-0 flex-1">
                <h2 className="truncate text-sm font-semibold">{title ?? "Source document"}</h2>
                <p className="truncate text-[11px] text-muted-foreground">
                  {data?.filename ?? "Loading…"}
                  {data?.total_rows != null ? ` · ${fmtNumber(data.total_rows)} rows` : ""}
                  {data?.truncated ? " · showing first 1,000" : ""}
                </p>
              </div>
              <Button
                variant="outline"
                size="sm"
                className="h-8"
                onClick={() => openWithToken(api.sourceFileUrl(module, "download"), true)}
              >
                <Download className="h-3.5 w-3.5" /> Download
              </Button>
              <Button variant="ghost" size="icon" onClick={onClose} aria-label="Close viewer">
                <X className="h-4 w-4" />
              </Button>
            </header>

            <div className="scrollbar-thin flex-1 overflow-auto">
              {content.isLoading ? (
                <div className="grid h-64 place-items-center text-muted-foreground">
                  <Loader2 className="h-5 w-5 animate-spin" />
                </div>
              ) : isPdf ? (
                pdfUrl ? (
                  <iframe
                    src={pdfUrl}
                    title={data?.filename ?? "Source PDF"}
                    className="h-[76vh] w-full border-0 bg-white"
                  />
                ) : (
                  <div className="grid h-64 place-items-center text-muted-foreground">
                    <Loader2 className="h-5 w-5 animate-spin" />
                  </div>
                )
              ) : !data?.supported ? (
                <div className="grid h-64 place-items-center p-6 text-center">
                  <div className="max-w-sm">
                    <AlertTriangle className="mx-auto h-7 w-7 text-warning" />
                    <p className="mt-2 text-sm font-medium">This file cannot be shown as a table</p>
                    <p className="mt-1 text-xs text-muted-foreground">
                      {data?.message ?? "The format is binary."} The archived copy is still available.
                    </p>
                    <div className="mt-3 flex justify-center gap-2">
                      <Button
                        size="sm"
                        onClick={() => openWithToken(api.sourceFileUrl(module, "view"))}
                      >
                        <ExternalLink className="h-3.5 w-3.5" /> Open file
                      </Button>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => openWithToken(api.sourceFileUrl(module, "download"), true)}
                      >
                        <Download className="h-3.5 w-3.5" /> Download
                      </Button>
                    </div>
                  </div>
                </div>
              ) : (
                <table className="data-table min-w-full text-xs">
                  <thead className="sticky top-0 z-10 bg-panel">
                    <tr>
                      <th className="w-12 text-right">#</th>
                      {(data.header ?? []).map((cell, index) => (
                        <th key={index} className="whitespace-nowrap">
                          {cell}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {(data.rows ?? []).map((row, rowIndex) => (
                      <tr key={rowIndex} className="hover:bg-muted/30">
                        <td className={cn("text-right tabular-nums text-muted-foreground")}>{rowIndex + 1}</td>
                        {(data.header ?? []).map((_, cellIndex) => (
                          <td key={cellIndex} className="max-w-[280px] truncate whitespace-nowrap">
                            {row[cellIndex] ?? ""}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </motion.div>
        </motion.div>
      ) : null}
    </AnimatePresence>
  );
}

async function fetchAuthedBlob(url: string): Promise<string> {
  const token = getToken();
  const headers: Record<string, string> = token ? { Authorization: `Bearer ${token}` } : {};
  const response = await fetch(url, { headers });
  const blob = await response.blob();
  return URL.createObjectURL(blob);
}

function openWithToken(url: string, download = false) {
  void fetchAuthedBlob(url).then((href) => {
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
