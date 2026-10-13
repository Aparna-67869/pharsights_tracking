"use client";

import * as React from "react";
import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { Network, Search, Share2, X } from "lucide-react";
import { api } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input, Select } from "@/components/ui/input";
import { Panel } from "@/components/common/panel";
import { KpiCard } from "@/components/common/kpi-card";
import { EmptyState } from "@/components/ui/skeleton";
import { ForceGraph, colorFor } from "@/components/graph/force-graph";
import { fmtNumber } from "@/lib/format";
import type { GraphNeighborhood, GraphNode } from "@/types/api";

const PRESETS = [
  { type: "drug", key: "atorvastatin", label: "Atorvastatin" },
  { type: "drug", key: "metformin", label: "Metformin" },
  { type: "drug", key: "apixaban", label: "Apixaban" },
];

export default function GraphPage() {
  const [nodeType, setNodeType] = React.useState("drug");
  const [key, setKey] = React.useState("");
  const [submitted, setSubmitted] = React.useState<{ type: string; key: string } | null>(null);
  const [depth, setDepth] = React.useState(2);
  const [selected, setSelected] = React.useState<GraphNode | null>(null);

  const stats = useQuery({ queryKey: ["graph-stats"], queryFn: () => api.graphStats() });
  const neighborhood = useQuery({
    queryKey: ["graph-nb", submitted?.type, submitted?.key, depth],
    queryFn: () => api.graphNeighborhood(submitted!.type, submitted!.key, depth),
    enabled: !!submitted,
  });

  const traverse = (type: string, value: string) => {
    if (!value.trim()) return;
    setSubmitted({ type, key: value.trim() });
    setSelected(null);
  };

  return (
    <div className="space-y-4">
      <header className="flex flex-col gap-2 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <h1 className="flex items-center gap-2 text-lg font-semibold tracking-tight">
            <Network className="h-4.5 w-4.5 text-primary" /> Knowledge Graph Explorer
          </h1>
          <p className="mt-0.5 text-xs text-muted-foreground">
            Drug → NDA/ANDA → Patent → PTE → FTF → Sponsor → Active Moiety → Orange Book, joined into a single
            traversable model.
          </p>
        </div>
        {stats.data ? (
          <div className="flex flex-wrap gap-2">
            <Badge variant="outline" className="gap-1">
              <Share2 className="h-3 w-3" /> {fmtNumber(Number(stats.data.node_count ?? 0))} nodes
            </Badge>
            <Badge variant="outline">{fmtNumber(Number(stats.data.edge_count ?? 0))} edges</Badge>
            <Badge variant="outline">{Object.keys(stats.data.nodes_by_type ?? {}).length} types</Badge>
          </div>
        ) : null}
      </header>

      {stats.data ? (
        <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <KpiCard label="Nodes" value={Number(stats.data.node_count ?? 0)} tone="primary" icon={<Share2 className="h-3.5 w-3.5 text-primary" />} />
          <KpiCard label="Relationships" value={Number(stats.data.edge_count ?? 0)} />
          <KpiCard label="Entity types" value={Object.keys(stats.data.nodes_by_type ?? {}).length} />
          <KpiCard label="Relation types" value={Object.keys(stats.data.edges_by_relation ?? {}).length} tone="success" />
        </section>
      ) : null}

      <Panel title="Traverse" subtitle="Pick an entity type and natural key" icon={<Search className="h-3.5 w-3.5" />}>
        <div className="flex flex-wrap items-end gap-2">
          <div className="space-y-1.5">
            <label className="text-[11px] text-muted-foreground">Node type</label>
            <Select value={nodeType} onChange={(event) => setNodeType(event.target.value)} className="h-9 w-48">
              {["drug", "anda", "nda", "patent", "ftf_record", "pte_application", "pte_certificate", "active_moiety", "sponsor"].map(
                (type) => (
                  <option key={type} value={type}>
                    {type.replace(/_/g, " ")}
                  </option>
                ),
              )}
            </Select>
          </div>
          <div className="min-w-[220px] flex-1 space-y-1.5">
            <label className="text-[11px] text-muted-foreground">Natural key</label>
            <Input
              value={key}
              onChange={(event) => setKey(event.target.value)}
              onKeyDown={(event) => event.key === "Enter" && traverse(nodeType, key)}
              placeholder="e.g. atorvastatin · 8357693 (patent) · 21652 (ANDA)"
              className="h-9"
            />
          </div>
          <div className="space-y-1.5">
            <label className="text-[11px] text-muted-foreground">Depth</label>
            <Select value={String(depth)} onChange={(event) => setDepth(Number(event.target.value))} className="h-9 w-24">
              {[1, 2, 3].map((value) => (
                <option key={value} value={value}>
                  {value}
                </option>
              ))}
            </Select>
          </div>
          <Button onClick={() => traverse(nodeType, key)} className="h-9">
            <Search className="h-3.5 w-3.5" /> Traverse
          </Button>
        </div>
        <div className="mt-2 flex flex-wrap items-center gap-1.5">
          <span className="text-[11px] text-muted-foreground">Try:</span>
          {PRESETS.map((preset) => (
            <button
              key={preset.key}
              onClick={() => {
                setNodeType(preset.type);
                setKey(preset.key);
                traverse(preset.type, preset.key);
              }}
              className="rounded-full border border-border/70 px-2 py-0.5 text-[11px] text-muted-foreground transition-colors hover:bg-muted/60 hover:text-foreground"
            >
              {preset.label}
            </button>
          ))}
        </div>
      </Panel>

      {!submitted ? (
        <EmptyState
          icon={<Network className="h-8 w-8" />}
          title="Traverse the graph"
          description="Enter a natural key to render its neighbourhood. Try a drug name, a patent number, an NDA/ANDA number or an FTF record key."
        />
      ) : neighborhood.isLoading ? (
        <Panel bodyClassName="grid h-[560px] place-items-center">
          <p className="text-xs text-muted-foreground">Traversing neighbourhood…</p>
        </Panel>
      ) : neighborhood.error ? (
        <EmptyState title="Node not found" description="No graph node matched that type and key." />
      ) : neighborhood.data ? (
        <GraphExplorer data={neighborhood.data} selected={selected} onSelect={setSelected} />
      ) : null}
    </div>
  );
}

function GraphExplorer({
  data,
  selected,
  onSelect,
}: {
  data: GraphNeighborhood;
  selected: GraphNode | null;
  onSelect: (node: GraphNode | null) => void;
}) {
  const relationGroups = React.useMemo(() => {
    const groups: Record<string, number> = {};
    data.edges.forEach((edge) => {
      groups[edge.relation] = (groups[edge.relation] ?? 0) + 1;
    });
    return groups;
  }, [data.edges]);

  const neighbours = React.useMemo(() => {
    if (!selected) return [];
    const ids = new Set<string>();
    data.edges.forEach((edge) => {
      if (edge.source === selected.id) ids.add(edge.target);
      if (edge.target === selected.id) ids.add(edge.source);
    });
    return data.nodes.filter((node) => ids.has(node.id)).slice(0, 12);
  }, [selected, data]);

  return (
    <div className="grid gap-4 xl:grid-cols-4">
      <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="xl:col-span-3">
        <Panel
          title={`Neighbourhood of ${data.root.label}`}
          subtitle={`${data.nodes.length} nodes · ${data.edges.length} relationships · hover to highlight, click to select, drag to pan, scroll to zoom`}
          tone="primary"
          bodyClassName="p-2"
        >
          <ForceGraph data={data} selectedId={selected?.id ?? null} onSelect={onSelect} />
        </Panel>
      </motion.div>

      <div className="space-y-4">
        <Panel
          title="Entity details"
          actions={
            selected ? (
              <Button variant="ghost" size="icon" className="h-6 w-6" onClick={() => onSelect(null)} aria-label="Clear selection">
                <X className="h-3.5 w-3.5" />
              </Button>
            ) : null
          }
        >
          {selected ? (
            <div className="space-y-2 text-xs">
              <div className="flex items-center gap-2">
                <span className="h-2.5 w-2.5 rounded-full" style={{ background: colorFor(selected.type) }} />
                <Badge variant="outline">{selected.type.replace(/_/g, " ")}</Badge>
                <span className="ml-auto text-[10px] text-muted-foreground">score {selected.importance}</span>
              </div>
              <p className="text-sm font-medium">{selected.label}</p>
              <p className="font-mono text-[10px] text-muted-foreground">{selected.key}</p>
              {neighbours.length ? (
                <div>
                  <p className="mb-1 text-[10px] uppercase tracking-wide text-muted-foreground">Connected</p>
                  <div className="flex flex-wrap gap-1">
                    {neighbours.map((node) => (
                      <button
                        key={node.id}
                        onClick={() => onSelect(node)}
                        className="rounded-full border border-border/70 px-2 py-0.5 text-[10px] hover:bg-muted/60"
                      >
                        {node.label.length > 22 ? `${node.label.slice(0, 21)}…` : node.label}
                      </button>
                    ))}
                  </div>
                </div>
              ) : null}
              <div className="space-y-1 border-t border-border/60 pt-2">
                {Object.entries(selected.properties ?? {}).slice(0, 10).map(([prop, value]) => (
                  <div key={prop} className="flex justify-between gap-2">
                    <span className="text-muted-foreground">{prop.replace(/_/g, " ")}</span>
                    <span className="max-w-[150px] truncate text-right">{String(value ?? "—")}</span>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <p className="text-xs text-muted-foreground">Click a node to inspect its properties and connections.</p>
          )}
        </Panel>

        <Panel title="Relationship mix">
          <div className="space-y-1.5 text-xs">
            {Object.entries(relationGroups)
              .sort((a, b) => b[1] - a[1])
              .map(([relation, count]) => (
                <div key={relation} className="flex items-center gap-2">
                  <span className="min-w-0 flex-1 truncate text-muted-foreground">{relation.replace(/_/g, " ")}</span>
                  <div className="h-1.5 w-20 overflow-hidden rounded-full bg-muted">
                    <div
                      className="h-full rounded-full bg-primary"
                      style={{ width: `${Math.min(100, (count / Math.max(...Object.values(relationGroups))) * 100)}%` }}
                    />
                  </div>
                  <span className="numeric w-6 text-right">{count}</span>
                </div>
              ))}
          </div>
        </Panel>
      </div>
    </div>
  );
}
