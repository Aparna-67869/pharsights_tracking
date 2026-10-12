"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { BrainCircuit, CornerDownLeft, Loader2, Search } from "lucide-react";
import { api } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

const ENTITY_LABELS: Record<string, string> = {
  drug: "Drug",
  ftf_record: "Paragraph IV",
  pte_application: "PTE Application",
  pte_certificate: "PTE Certificate",
  active_moiety: "Active Moiety",
  orange_book_product: "Orange Book",
  orange_book_patent: "OB Patent",
  patent: "Patent",
  sponsor: "Sponsor",
};

export function CommandPalette({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const router = useRouter();
  const [query, setQuery] = React.useState("");
  const [debounced, setDebounced] = React.useState("");

  React.useEffect(() => {
    const timer = setTimeout(() => setDebounced(query.trim()), 220);
    return () => clearTimeout(timer);
  }, [query]);

  const { data, isFetching } = useQuery({
    queryKey: ["palette-search", debounced],
    queryFn: () => api.search(debounced, 12),
    enabled: open && debounced.length > 1,
  });

  React.useEffect(() => {
    if (!open) {
      setQuery("");
      setDebounced("");
    }
  }, [open]);

  if (!open) return null;

  const hits = data?.hits ?? [];

  const go = (path: string) => {
    onOpenChange(false);
    router.push(path);
  };

  return (
    <div className="fixed inset-0 z-[60] flex items-start justify-center bg-background/70 p-4 pt-[12vh] backdrop-blur-sm">
      <div className="absolute inset-0" onClick={() => onOpenChange(false)} />
      <div className="glass-strong relative z-10 w-full max-w-2xl overflow-hidden rounded-2xl">
        <div className="flex items-center gap-3 border-b border-border/70 px-4 py-3">
          <Search className="h-4 w-4 text-muted-foreground" />
          <input
            autoFocus
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                if (hits[0]) go(`/search?q=${encodeURIComponent(hits[0].title)}`);
                else if (query.trim()) go(`/search?q=${encodeURIComponent(query.trim())}`);
              }
              if (event.key === "Escape") onOpenChange(false);
            }}
            placeholder="Search drugs, patents, NDA/ANDA, sponsors, moieties…"
            className="flex-1 bg-transparent text-sm outline-none placeholder:text-muted-foreground"
          />
          {isFetching ? <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" /> : null}
          <kbd className="rounded border border-border bg-muted/60 px-1.5 py-0.5 text-[10px]">esc</kbd>
        </div>

        <div className="scrollbar-thin max-h-[52vh] overflow-y-auto">
          {debounced.length <= 1 ? (
            <div className="p-4">
              <button
                onClick={() => go(`/copilot${query.trim() ? `?q=${encodeURIComponent(query.trim())}` : ""}`)}
                className="flex w-full items-center gap-3 rounded-lg border border-border/70 bg-surface/50 px-3 py-2.5 text-left text-sm transition-colors hover:bg-muted/50"
              >
                <BrainCircuit className="h-4 w-4 text-primary" />
                <span className="flex-1">
                  Ask the copilot{query.trim() ? `: “${query.trim()}”` : ""}
                </span>
                <Badge variant="secondary">AI</Badge>
              </button>
              <p className="px-1 pt-3 text-[11px] text-muted-foreground">
                Type at least two characters to search across every module.
              </p>
            </div>
          ) : hits.length === 0 && !isFetching ? (
            <p className="px-4 py-6 text-center text-xs text-muted-foreground">
              No records matched “{debounced}”.
            </p>
          ) : (
            <ul className="p-2">
              {hits.map((hit) => (
                <li key={`${hit.entity_type}-${hit.id}`}>
                  <button
                    onClick={() => go(`/search?q=${encodeURIComponent(hit.title)}`)}
                    className="flex w-full items-center gap-3 rounded-lg px-3 py-2 text-left transition-colors hover:bg-muted/50"
                  >
                    <span className="flex-1 truncate">
                      <span className="text-sm font-medium">{hit.title}</span>
                      {hit.subtitle ? (
                        <span className="ml-2 text-xs text-muted-foreground">{hit.subtitle}</span>
                      ) : null}
                    </span>
                    <Badge variant="outline" className={cn("shrink-0")}>
                      {ENTITY_LABELS[hit.entity_type] ?? hit.entity_type}
                    </Badge>
                    <CornerDownLeft className="h-3.5 w-3.5 text-muted-foreground" />
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}
