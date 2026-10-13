"use client";

import * as React from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { CalendarClock, Search, ShieldCheck, Target } from "lucide-react";
import { api } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input, Select } from "@/components/ui/input";
import { Panel } from "@/components/common/panel";
import { KpiCard } from "@/components/common/kpi-card";
import { BarSeries } from "@/components/charts/charts";
import { TableSkeleton } from "@/components/ui/skeleton";
import { fmtNumber } from "@/lib/format";
import { cn } from "@/lib/utils";

/**
 * Patent intelligence: the listed-patent expiry runway, with the opportunity
 * engine's scoring layered on top so the list reads as a triage queue rather
 * than a raw dump.
 */
export default function PatentsPage() {
  const [page, setPage] = React.useState(1);
  const [view, setView] = React.useState<"watchlist" | "all">("watchlist");
  const [search, setSearch] = React.useState("");
  const [applied, setApplied] = React.useState("");

  React.useEffect(() => setPage(1), [view, applied]);

  const opportunities = useQuery({ queryKey: ["opportunities"], queryFn: () => api.opportunities() });
  const patents = useQuery({
    queryKey: ["ob-patents", page, applied],
    queryFn: () => api.obPatents({ page, page_size: 25, patent_number: applied || undefined }),
  });
  const charts = useQuery({ queryKey: ["charts"], queryFn: () => api.charts(), staleTime: 60_000 });

  const bands = opportunities.data?.by_band ?? {};

  return (
    <div className="space-y-4">
      <header className="flex flex-col gap-2 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <h1 className="flex items-center gap-2 text-lg font-semibold tracking-tight">
            <ShieldCheck className="h-4.5 w-4.5 text-primary" /> Patent Intelligence
          </h1>
          <p className="mt-0.5 text-xs text-muted-foreground">
            Orange Book listed patents, expiry runway and scored generic-entry opportunities.
          </p>
        </div>
        <Link href="/copilot">
          <Button size="sm" variant="outline">
            <Target className="h-3.5 w-3.5" /> Ask about a patent
          </Button>
        </Link>
      </header>

      <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <KpiCard label="Opportunities scored" value={opportunities.data?.total ?? 0} tone="primary" icon={<Target className="h-3.5 w-3.5 text-primary" />} />
        <KpiCard label="High band" value={bands.high ?? 0} tone="success" />
        <KpiCard label="Medium band" value={bands.medium ?? 0} tone="warning" />
        <KpiCard label="Watch band" value={bands.watch ?? 0} />
      </section>

      <div className="flex flex-wrap items-center gap-2">
        <Select value={view} onChange={(e) => setView(e.target.value as typeof view)} className="h-8 w-48 text-xs">
          <option value="watchlist">Opportunity watchlist</option>
          <option value="all">All listed patents</option>
        </Select>
        {view === "all" ? (
          <>
            <Input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && setApplied(search)}
              placeholder="Patent number…"
              className="h-8 w-44 text-xs"
            />
            <Button variant="outline" size="sm" onClick={() => setApplied(search)}>
              <Search className="h-3 w-3" /> Filter
            </Button>
          </>
        ) : null}
        <span className="ml-auto text-xs text-muted-foreground">
          {view === "all" ? `${patents.data?.total ?? 0} patents` : `${opportunities.data?.top.length ?? 0} scored`}
        </span>
      </div>

      {view === "watchlist" ? (
        <div className="grid gap-4 xl:grid-cols-12">
          <div className="xl:col-span-8">
            <Panel title="Opportunity watchlist" subtitle="Ranked by entry score — nearest expiries with the least crowding" tone="warning" bodyClassName="p-0">
              <div className="scrollbar-thin max-h-[520px] overflow-y-auto">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>#</th>
                      <th>Product / patent</th>
                      <th className="hidden md:table-cell">Sponsor</th>
                      <th>Expiry</th>
                      <th>Score</th>
                    </tr>
                  </thead>
                  <tbody>
                    {opportunities.isLoading ? (
                      <tr><td colSpan={5} className="py-8 text-center text-xs text-muted-foreground">Scoring…</td></tr>
                    ) : (opportunities.data?.top.length ?? 0) === 0 ? (
                      <tr><td colSpan={5} className="py-8 text-center text-xs text-muted-foreground">No near-term expiries detected.</td></tr>
                    ) : (
                      opportunities.data?.top.map((row, index) => (
                        <tr key={`${row.patent_number}-${index}`}>
                          <td className="numeric text-muted-foreground">{index + 1}</td>
                          <td>
                            <p className="text-xs font-medium">{row.trade_name ?? row.ingredient}</p>
                            <p className="font-mono text-[10px] text-muted-foreground">{row.appl_no} · US{row.patent_number}</p>
                          </td>
                          <td className="hidden max-w-[160px] truncate text-[11px] text-muted-foreground md:table-cell">{row.applicant ?? "—"}</td>
                          <td className="text-[11px] text-muted-foreground">
                            {row.expiration_date ?? "—"}
                            {row.months_to_expiry != null ? <span className="ml-1 text-muted-foreground/70">({row.months_to_expiry}m)</span> : null}
                          </td>
                          <td>
                            <div className="flex items-center gap-2">
                              <div className="h-1.5 w-16 overflow-hidden rounded-full bg-muted">
                                <motion.div
                                  initial={{ width: 0 }}
                                  animate={{ width: `${row.opportunity_score}%` }}
                                  transition={{ duration: 0.5, delay: index * 0.03 }}
                                  className={cn("h-full rounded-full", row.band === "high" ? "bg-success" : row.band === "medium" ? "bg-warning" : "bg-primary")}
                                />
                              </div>
                              <span className="numeric w-7 text-right text-[11px]">{row.opportunity_score}</span>
                            </div>
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </Panel>
          </div>
          <div className="space-y-4 xl:col-span-4">
            {charts.data ? (
              <BarSeries
                title="Expiries by year"
                subtitle="Listed patents expiring each year"
                data={charts.data.patent_expiry_timeline}
                xKey="year"
                bars={[{ key: "count", label: "Patents" }]}
                height={260}
              />
            ) : null}
            <Panel title="Scoring model" subtitle="How the entry score is built">
              <ul className="space-y-1.5 text-[11px] text-muted-foreground">
                <li>· Time to expiry — nearer expiry scores higher, decaying past 36 months.</li>
                <li>· Crowding — each additional listed patent on the same application penalises the score.</li>
                <li>· Bands — high ≥75, medium ≥50, watch ≥25.</li>
              </ul>
            </Panel>
          </div>
        </div>
      ) : patents.isLoading ? (
        <TableSkeleton rows={8} cols={5} />
      ) : (
        <Panel title="Listed patents" subtitle="Orange Book patent listings" bodyClassName="p-0">
          <div className="scrollbar-thin overflow-x-auto">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Patent</th>
                  <th>Application</th>
                  <th>Expiration</th>
                  <th>Substance</th>
                  <th>Product</th>
                  <th>Use code</th>
                </tr>
              </thead>
              <tbody>
                {(patents.data?.items.length ?? 0) === 0 ? (
                  <tr><td colSpan={6} className="py-8 text-center text-xs text-muted-foreground">No patents matched.</td></tr>
                ) : (
                  patents.data?.items.map((patent) => (
                    <tr key={patent.id}>
                      <td className="font-mono text-[11px]">US{patent.patent_number}</td>
                      <td className="text-[11px]">{patent.appl_type}{patent.appl_no}</td>
                      <td className="text-[11px]">
                        {patent.expiration_date ? (
                          <span className="inline-flex items-center gap-1">
                            <CalendarClock className="h-3 w-3 text-muted-foreground" />
                            {patent.expiration_date}
                          </span>
                        ) : (
                          "—"
                        )}
                      </td>
                      <td>{patent.drug_substance_flag ? <Badge variant="success">yes</Badge> : <span className="text-muted-foreground">—</span>}</td>
                      <td>{patent.drug_product_flag ? <Badge variant="secondary">yes</Badge> : <span className="text-muted-foreground">—</span>}</td>
                      <td className="font-mono text-[11px] text-muted-foreground">{patent.patent_use_code ?? "—"}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
          <div className="flex items-center justify-between border-t border-border/60 px-3 py-2 text-xs text-muted-foreground">
            <span>Page {patents.data?.page} of {patents.data?.pages} · {fmtNumber(patents.data?.total ?? 0)} total</span>
            <div className="flex gap-2">
              <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage((v) => v - 1)}>Prev</Button>
              <Button variant="outline" size="sm" disabled={page >= (patents.data?.pages ?? 1)} onClick={() => setPage((v) => v + 1)}>Next</Button>
            </div>
          </div>
        </Panel>
      )}
    </div>
  );
}
