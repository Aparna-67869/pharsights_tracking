"use client";

import * as React from "react";
import { ShieldCheck } from "lucide-react";
import { hasRaw } from "@/lib/format";

/**
 * Renders the exact cell text preserved from the official source document.
 * Shown when a table row is expanded so any value on the dashboard can be
 * verified against the file the regulator published.
 */
export function SourceCells({ raw }: { raw?: Record<string, unknown> | null }) {
  if (!hasRaw({ raw })) {
    return (
      <p className="text-[11px] text-muted-foreground">
        No preserved source cells recorded for this row.
      </p>
    );
  }
  const entries = Object.entries(raw as Record<string, unknown>).filter(
    ([, value]) => value != null && String(value) !== "",
  );
  return (
    <div>
      <p className="mb-2 inline-flex items-center gap-1.5 text-[11px] font-medium text-muted-foreground">
        <ShieldCheck className="h-3.5 w-3.5 text-success" />
        Exact values published in the source document
      </p>
      <dl className="grid grid-cols-1 gap-x-6 gap-y-1.5 text-xs sm:grid-cols-2 lg:grid-cols-3">
        {entries.map(([key, value]) => (
          <div key={key} className="flex min-w-0 flex-col border-b border-border/40 pb-1">
            <dt className="truncate text-[10px] uppercase tracking-wide text-muted-foreground">{key}</dt>
            <dd className="break-words font-medium">{String(value)}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}
