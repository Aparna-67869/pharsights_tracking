"use client";

import * as React from "react";
import { useQuery } from "@tanstack/react-query";
import { Download, FileText, ShieldCheck } from "lucide-react";
import { api } from "@/lib/api";
import { openWithToken } from "@/lib/files";
import { Button } from "@/components/ui/button";
import { fmtDate } from "@/lib/format";

/**
 * Prominent, always-visible access to the regulator's own document.
 *
 * Requirement 1.A: users must be able to open the official source (for FTF the
 * FDA Paragraph IV Certifications List PDF) without leaving the platform. The
 * copy is the platform-archived artifact, so it works even when the desktop
 * cannot reach fda.gov directly.
 */
export function OfficialSourceBanner({ module }: { module: string }) {
  const source = useQuery({
    queryKey: ["module-source", module],
    queryFn: () => api.moduleSource(module),
    staleTime: 60_000,
  });

  const data = source.data;
  if (!data) return null;

  const label = data.official_document_label ?? "View Official regulator document";
  const published = data.publication_date ? data.publication_label ?? fmtDate(data.publication_date) : null;

  return (
    <div className="panel flex flex-col gap-3 border-primary/30 bg-gradient-to-r from-primary/10 via-primary/5 to-transparent px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
      <div className="flex items-start gap-3">
        <span className="mt-0.5 grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-primary/15 text-primary ring-1 ring-primary/25">
          <ShieldCheck className="h-5 w-5" />
        </span>
        <div className="min-w-0">
          <p className="text-sm font-semibold">Official source document</p>
          <p className="text-xs text-muted-foreground">
            {data.source_name ?? "Regulator document"}
            {published ? ` · published ${published}` : ""}
            {data.filename ? ` · ${data.filename}` : ""}
            {data.version && data.version > 1 ? ` · v${data.version}` : ""}
          </p>
        </div>
      </div>
      <div className="flex shrink-0 items-center gap-2">
        <Button
          className="shadow-glow"
          onClick={() => openWithToken(api.officialDocumentUrl(module, "view"))}
        >
          <FileText className="h-4 w-4" /> {label}
        </Button>
        <Button
          variant="outline"
          onClick={() => openWithToken(api.officialDocumentUrl(module, "download"), true)}
          title="Download the official document"
        >
          <Download className="h-4 w-4" /> Download
        </Button>
      </div>
    </div>
  );
}
