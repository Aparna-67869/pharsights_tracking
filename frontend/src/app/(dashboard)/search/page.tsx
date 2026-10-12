"use client";

import * as React from "react";
import { useSearchParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import {
  Building2,
  FileText,
  FlaskConical,
  GitCompareArrows,
  Layers,
  Search,
  ShieldAlert,
  Sparkles,
  X,
} from "lucide-react";
import { api } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { EmptyState, TableSkeleton } from "@/components/ui/skeleton";
import { fmtDate, fmtExtension, PRIORITY_STYLES } from "@/lib/format";
import { cn } from "@/lib/utils";
import { useDebounced } from "@/hooks/use-debounce";
import type { SearchHit } from "@/types/api";

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

export default function SearchPage() {
  const params = useSearchParams();
  const [query, setQuery] = React.useState(params.get("q") ?? "");
  const [selected, setSelected] = React.useState<SearchHit | null>(null);
  const debounced = useDebounced(query, 320);

  const results = useQuery({
    queryKey: ["search", debounced],
    queryFn: () => api.search(debounced, 40),
    enabled: debounced.trim().length > 1,
  });

  const drugHit = React.useMemo(() => {
    if (selected?.entity_type === "drug") return selected;
    return results.data?.hits.find((hit) => hit.entity_type === "drug") ?? null;
  }, [selected, results.data]);

  const facets = results.data?.facets ?? {};

  return (
    <div className="space-y-5">
      <header>
        <h1 className="flex items-center gap-2 text-xl font-semibold">
          <Search className="h-5 w-5 text-primary" /> Global Search
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">
          One query across drugs, patents, NDA/ANDA, sponsors, active moieties and Orange Book records — with
          a 360° view of the selected drug.
        </p>
      </header>

      <Card className="p-4">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            autoFocus
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Try “Lipitor”, a patent number, an NDA/ANDA, a sponsor, or an active moiety…"
            className="h-11 pl-10 pr-9 text-base"
          />
          {query ? (
            <button
              onClick={() => setQuery("")}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
            >
              <X className="h-4 w-4" />
            </button>
          ) : null}
        </div>
        {Object.keys(facets).length ? (
          <div className="mt-3 flex flex-wrap items-center gap-1.5">
            <span className="text-[11px] text-muted-foreground">Results:</span>
            {Object.entries(facets).map(([type, count]) => (
              <Badge key={type} variant="secondary">
                {ENTITY_LABELS[type] ?? type} · {count}
              </Badge>
            ))}
          </div>
        ) : null}
      </Card>

      {debounced.trim().length <= 1 ? (
        <EmptyState
          icon={<Search className="h-8 w-8" />}
          title="Start typing to search"
          description="The search box understands drug names, patent numbers, NDA/ANDA numbers, sponsors, active moieties, NCT IDs and therapy areas."
        />
      ) : results.isLoading ? (
        <TableSkeleton rows={6} cols={3} />
      ) : (
        <div className="grid gap-4 xl:grid-cols-5">
          <div className="space-y-2 xl:col-span-3">
            <p className="text-xs text-muted-foreground">
              {results.data?.total ?? 0} result{(results.data?.total ?? 0) === 1 ? "" : "s"} for “
              {results.data?.query}”
            </p>
            {(results.data?.hits ?? []).map((hit) => (
              <button
                key={`${hit.entity_type}-${hit.id}`}
                onClick={() => setSelected(hit)}
                className={cn(
                  "w-full rounded-xl border p-3 text-left transition-colors",
                  selected?.id === hit.id
                    ? "border-primary/40 bg-primary/8"
                    : "border-border/70 bg-card/60 hover:bg-muted/40",
                )}
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium">{hit.title}</p>
                    {hit.subtitle ? (
                      <p className="truncate text-xs text-muted-foreground">{hit.subtitle}</p>
                    ) : null}
                  </div>
                  <Badge variant="outline">{ENTITY_LABELS[hit.entity_type] ?? hit.entity_type}</Badge>
                </div>
                <p className="mt-1 text-[10px] text-muted-foreground">matched on {hit.matched_on}</p>
              </button>
            ))}
            {(results.data?.hits.length ?? 0) === 0 ? (
              <EmptyState title="No records matched" description="Try a shorter or differently-spelled query." />
            ) : null}
          </div>

          <div className="xl:col-span-2">
            {drugHit ? (
              <Drug360 drugId={drugHit.id} name={drugHit.title} />
            ) : (
              <Card>
                <CardContent>
                  <EmptyState
                    icon={<Layers className="h-8 w-8" />}
                    title="360° view"
                    description="Select a drug result to see its NDA, ANDA, patents, PTE, PDE, Orange Book records and related insights in one place."
                  />
                </CardContent>
              </Card>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

interface Drug360Data {
  drug?: Record<string, unknown>;
  sponsor?: { id: string; name: string } | null;
  paragraph_iv_filings?: Array<Record<string, unknown>>;
  pte_applications?: Array<Record<string, unknown>>;
  pte_certificates?: Array<Record<string, unknown>>;
  active_moieties?: Array<Record<string, unknown>>;
  patents?: Array<Record<string, unknown>>;
  orange_book_products?: Array<Record<string, unknown>>;
  orange_book_patents?: Array<Record<string, unknown>>;
  orange_book_exclusivity?: Array<Record<string, unknown>>;
  insights?: Array<Record<string, unknown>>;
}

function Drug360({ drugId, name }: { drugId: string; name: string }) {
  const { data, isLoading } = useQuery({
    queryKey: ["drug-360", drugId],
    queryFn: () => api.drug360(drugId) as unknown as Promise<Drug360Data>,
  });

  const sections: Array<{ key: string; label: string; icon: React.ReactNode; count: number }> = [
    { key: "paragraph_iv_filings", label: "Paragraph IV", icon: <GitCompareArrows className="h-3.5 w-3.5" />, count: data?.paragraph_iv_filings?.length ?? 0 },
    { key: "pte_applications", label: "PTE apps", icon: <FileText className="h-3.5 w-3.5" />, count: data?.pte_applications?.length ?? 0 },
    { key: "pte_certificates", label: "PTE grants", icon: <FileText className="h-3.5 w-3.5" />, count: data?.pte_certificates?.length ?? 0 },
    { key: "active_moieties", label: "Moieties", icon: <FlaskConical className="h-3.5 w-3.5" />, count: data?.active_moieties?.length ?? 0 },
    { key: "patents", label: "Patents", icon: <Layers className="h-3.5 w-3.5" />, count: data?.patents?.length ?? 0 },
    { key: "orange_book_products", label: "Orange Book", icon: <Layers className="h-3.5 w-3.5" />, count: data?.orange_book_products?.length ?? 0 },
  ];

  if (isLoading) return <TableSkeleton rows={6} cols={1} />;

  return (
    <Card className="overflow-hidden">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Layers className="h-4 w-4 text-primary" /> 360° view — {name}
        </CardTitle>
        {data?.sponsor ? (
          <p className="mt-0.5 flex items-center gap-1.5 text-xs text-muted-foreground">
            <Building2 className="h-3 w-3" /> {data.sponsor.name}
          </p>
        ) : null}
      </CardHeader>
      <CardContent className="p-0">
        <div className="grid grid-cols-3 gap-px border-b border-border/70 bg-border/60">
          {sections.map((section) => (
            <div key={section.key} className="bg-card p-3 text-center">
              <div className="flex items-center justify-center gap-1 text-muted-foreground">
                {section.icon}
                <span className="text-[10px] uppercase tracking-wide">{section.label}</span>
              </div>
              <p className="mt-1 text-lg font-semibold tabular-nums">{section.count}</p>
            </div>
          ))}
        </div>

        <Tabs defaultValue="paragraph_iv_filings" className="p-3">
          <TabsList className="flex-wrap">
            <TabsTrigger value="paragraph_iv_filings">Paragraph IV</TabsTrigger>
            <TabsTrigger value="pte_certificates">PTE</TabsTrigger>
            <TabsTrigger value="patents">Patents</TabsTrigger>
            <TabsTrigger value="orange_book_products">Orange Book</TabsTrigger>
            <TabsTrigger value="insights">Insights</TabsTrigger>
          </TabsList>

          <TabsContent value="paragraph_iv_filings" className="mt-3">
            <RowList
              rows={data?.paragraph_iv_filings}
              empty="No Paragraph IV certifications on record."
              render={(row) => (
                <>
                  <span className="font-medium">NDA {String(row.nda_number ?? "—")}</span>
                  <span className="text-muted-foreground">{String(row.rld_brand_name ?? "")}</span>
                  <span className="ml-auto flex items-center gap-2">
                    {row.exclusivity_status ? (
                      <Badge variant={String(row.exclusivity_status).toLowerCase() === "eligible" ? "success" : "secondary"}>
                        {String(row.exclusivity_status)}
                      </Badge>
                    ) : null}
                    <span className="text-[10px] text-muted-foreground">{fmtDate(row.date_of_submission as string)}</span>
                  </span>
                </>
              )}
            />
          </TabsContent>

          <TabsContent value="pte_certificates" className="mt-3">
            <RowList
              rows={data?.pte_certificates}
              empty="No patent term extensions granted."
              render={(row) => (
                <>
                  <span className="font-mono text-xs">{String(row.patent_number ?? "—")}</span>
                  <Badge variant="secondary">{fmtExtension(row.extension_days as number)}</Badge>
                  <span className="ml-auto text-[10px] text-muted-foreground">
                    expires {fmtDate(row.extended_expiration_date as string)}
                  </span>
                </>
              )}
            />
          </TabsContent>

          <TabsContent value="patents" className="mt-3">
            <RowList
              rows={data?.patents}
              empty="No linked patents."
              render={(row) => (
                <>
                  <span className="font-mono text-xs">{String(row.patent_number ?? "—")}</span>
                  <div className="flex gap-1">
                    {row.has_pte ? <Badge variant="success">PTE</Badge> : null}
                    {row.has_paragraph_iv ? <Badge variant="warning">Para IV</Badge> : null}
                  </div>
                  <span className="ml-auto text-[10px] text-muted-foreground">
                    expires {fmtDate(row.expiration_date as string)}
                  </span>
                </>
              )}
            />
          </TabsContent>

          <TabsContent value="orange_book_products" className="mt-3">
            <RowList
              rows={data?.orange_book_products}
              empty="No Orange Book listing."
              render={(row) => (
                <>
                  <span className="font-mono text-xs">{String(row.application ?? "—")}</span>
                  <span className="font-medium">{String(row.trade_name ?? "—")}</span>
                  {row.te_code ? <Badge variant="secondary">{String(row.te_code)}</Badge> : null}
                  <span className="ml-auto text-[10px] text-muted-foreground">
                    approved {fmtDate(row.approval_date as string)}
                  </span>
                </>
              )}
            />
          </TabsContent>

          <TabsContent value="insights" className="mt-3">
            <div className="space-y-2">
              {(data?.insights ?? []).length === 0 ? (
                <p className="py-6 text-center text-xs text-muted-foreground">
                  No AI insights recorded for this drug.
                </p>
              ) : (
                (data?.insights ?? []).map((insight) => (
                  <div key={String(insight.id)} className="rounded-lg border border-border/70 bg-surface/40 p-3">
                    <div className="flex items-center gap-2">
                      <Badge className={cn("border", PRIORITY_STYLES[String(insight.priority_label)] ?? "")}>
                        {String(insight.priority_label).toUpperCase()} {String(insight.priority_score)}
                      </Badge>
                    </div>
                    <p className="mt-1 text-sm font-medium">{String(insight.title)}</p>
                    {insight.recommended_action ? (
                      <p className="mt-0.5 flex items-start gap-1.5 text-[11px] text-muted-foreground">
                        <ShieldAlert className="mt-0.5 h-3 w-3 shrink-0" />
                        {String(insight.recommended_action)}
                      </p>
                    ) : null}
                  </div>
                ))
              )}
            </div>
          </TabsContent>
        </Tabs>
      </CardContent>
      <div className="flex items-center gap-2 border-t border-border/70 px-4 py-2">
        <Sparkles className="h-3 w-3 text-primary" />
        <span className="text-[10px] text-muted-foreground">
          Assembled from every monitored source through the knowledge graph.
        </span>
      </div>
    </Card>
  );
}

function RowList({
  rows,
  empty,
  render,
}: {
  rows?: Array<Record<string, unknown>>;
  empty: string;
  render: (row: Record<string, unknown>) => React.ReactNode;
}) {
  if (!rows || rows.length === 0) {
    return <p className="py-6 text-center text-xs text-muted-foreground">{empty}</p>;
  }
  return (
    <div className="scrollbar-thin max-h-[38vh] space-y-1.5 overflow-y-auto">
      {rows.map((row, index) => (
        <div
          key={String(row.id ?? index)}
          className="flex flex-wrap items-center gap-2 rounded-lg border border-border/70 bg-surface/40 px-3 py-2 text-xs"
        >
          {render(row)}
        </div>
      ))}
    </div>
  );
}
