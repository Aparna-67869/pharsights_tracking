"use client";

import * as React from "react";
import { useQuery } from "@tanstack/react-query";
import { Network, Search, Share2 } from "lucide-react";
import { api } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input, Select } from "@/components/ui/input";
import { EmptyState } from "@/components/ui/skeleton";
import { KpiCard } from "@/components/common/kpi-card";
import { fmtNumber } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { GraphNeighborhood, GraphNode } from "@/types/api";

const TYPE_COLORS: Record<string, string> = {
  drug: "hsl(217 91% 60%)",
  anda: "hsl(142 69% 50%)",
  nda: "hsl(199 89% 55%)",
  patent: "hsl(280 65% 62%)",
  ftf_record: "hsl(38 92% 55%)",
  pte_application: "hsl(20 85% 58%)",
  pte_certificate: "hsl(340 75% 60%)",
  active_moiety: "hsl(170 70% 45%)",
  sponsor: "hsl(48 90% 55%)",
  orange_book_record: "hsl(0 63% 55%)",
};

export default function GraphPage() {
  const [nodeType, setNodeType] = React.useState("drug");
  const [key, setKey] = React.useState("");
  const [submitted, setSubmitted] = React.useState("");
  const [depth, setDepth] = React.useState(2);

  const stats = useQuery({ queryKey: ["graph-stats"], queryFn: () => api.graphStats() });

  const neighborhood = useQuery({
    queryKey: ["graph-nb", nodeType, submitted, depth],
    queryFn: () => api.graphNeighborhood(nodeType, submitted, depth),
    enabled: submitted.trim().length > 0,
  });

  return (
    <div className="space-y-5">
      <header>
        <h1 className="flex items-center gap-2 text-xl font-semibold">
          <Network className="h-5 w-5 text-primary" /> Knowledge Graph
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Drug → NDA/ANDA → Patent → PTE → FTF → Sponsor → Active Moiety → Orange Book, joined into a single
          traversable model for 360° product intelligence.
        </p>
      </header>

      {stats.data ? (
        <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <KpiCard label="Nodes" value={Number(stats.data.node_count ?? 0)} tone="primary" icon={<Share2 className="h-4 w-4" />} />
          <KpiCard label="Edges" value={Number(stats.data.edge_count ?? 0)} />
          <KpiCard label="Node types" value={Object.keys(stats.data.nodes_by_type ?? {}).length} />
          <KpiCard label="Relations" value={Object.keys(stats.data.edges_by_relation ?? {}).length} tone="success" />
        </section>
      ) : null}

      <Card className="p-4">
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
              onKeyDown={(event) => event.key === "Enter" && setSubmitted(key)}
              placeholder="e.g. atorvastatin (drug), 8357693 (patent), 21652 (ANDA)"
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
          <Button onClick={() => setSubmitted(key)} className="h-9">
            <Search className="h-3.5 w-3.5" /> Traverse
          </Button>
        </div>
      </Card>

      {!submitted ? (
        <EmptyState
          icon={<Network className="h-8 w-8" />}
          title="Traverse the graph"
          description="Enter a natural key to render its neighbourhood. Try a drug name, a patent number, an NDA/ANDA number or an FTF record key."
        />
      ) : neighborhood.isLoading ? (
        <Card className="grid h-[480px] place-items-center">
          <p className="text-xs text-muted-foreground">Traversing neighbourhood…</p>
        </Card>
      ) : neighborhood.error ? (
        <EmptyState title="Node not found" description="No graph node matched that type and key." />
      ) : neighborhood.data ? (
        <GraphCanvas data={neighborhood.data} />
      ) : null}
    </div>
  );
}

function GraphCanvas({ data }: { data: GraphNeighborhood }) {
  const [hovered, setHovered] = React.useState<GraphNode | null>(null);
  const width = 960;
  const height = 520;
  const cx = width / 2;
  const cy = height / 2;

  // Deterministic radial layout: root at the centre, neighbours on rings by relation.
  const layout = React.useMemo(() => {
    const byId = new Map<string, { x: number; y: number }>();
    byId.set(data.root.id, { x: cx, y: cy });
    const others = data.nodes.filter((node) => node.id !== data.root.id);
    const rings = [Math.min(others.length, 12), Math.max(0, others.length - 12)];
    let index = 0;
    rings.forEach((count, ringIndex) => {
      const radius = 130 + ringIndex * 105;
      for (let i = 0; i < count; i += 1) {
        const node = others[index];
        if (!node) break;
        const angle = (2 * Math.PI * i) / Math.max(count, 1) - Math.PI / 2 + ringIndex * 0.4;
        byId.set(node.id, { x: cx + radius * Math.cos(angle), y: cy + radius * Math.sin(angle) });
        index += 1;
      }
    });
    return byId;
  }, [data, cx, cy]);

  const relationGroups = React.useMemo(() => {
    const groups: Record<string, number> = {};
    data.edges.forEach((edge) => {
      groups[edge.relation] = (groups[edge.relation] ?? 0) + 1;
    });
    return groups;
  }, [data.edges]);

  return (
    <div className="grid gap-4 xl:grid-cols-4">
      <Card className="overflow-hidden xl:col-span-3">
        <CardHeader>
          <CardTitle>
            Neighbourhood of <span className="font-mono text-xs">{data.root.label}</span>
          </CardTitle>
          <p className="mt-0.5 text-xs text-muted-foreground">
            {data.nodes.length} nodes · {data.edges.length} relationships
          </p>
        </CardHeader>
        <CardContent>
          <div className="scrollbar-thin overflow-auto rounded-lg border border-border/70 bg-surface-muted/30">
            <svg viewBox={`0 0 ${width} ${height}`} className="h-auto w-full min-w-[720px]">
              <defs>
                <marker id="arrow" markerWidth="8" markerHeight="8" refX="16" refY="4" orient="auto">
                  <path d="M0,0 L8,4 L0,8 z" fill="hsl(var(--muted-foreground))" opacity="0.6" />
                </marker>
              </defs>

              {data.edges.map((edge) => {
                const from = layout.get(edge.source);
                const to = layout.get(edge.target);
                if (!from || !to) return null;
                const active = hovered && (hovered.id === edge.source || hovered.id === edge.target);
                return (
                  <g key={edge.id}>
                    <line
                      x1={from.x}
                      y1={from.y}
                      x2={to.x}
                      y2={to.y}
                      stroke={active ? "hsl(var(--primary))" : "hsl(var(--muted-foreground))"}
                      strokeOpacity={active ? 0.9 : 0.28}
                      strokeWidth={active ? 1.6 : 1}
                      markerEnd="url(#arrow)"
                    />
                    {active ? (
                      <text
                        x={(from.x + to.x) / 2}
                        y={(from.y + to.y) / 2 - 3}
                        fontSize="9"
                        textAnchor="middle"
                        fill="hsl(var(--muted-foreground))"
                      >
                        {edge.relation}
                      </text>
                    ) : null}
                  </g>
                );
              })}

              {data.nodes.map((node) => {
                const position = layout.get(node.id);
                if (!position) return null;
                const isRoot = node.id === data.root.id;
                const radius = isRoot ? 14 : 7 + Math.min(node.importance, 100) / 14;
                const color = TYPE_COLORS[node.type] ?? "hsl(var(--muted-foreground))";
                return (
                  <g
                    key={node.id}
                    onMouseEnter={() => setHovered(node)}
                    onMouseLeave={() => setHovered(null)}
                    className="cursor-pointer"
                  >
                    <circle
                      cx={position.x}
                      cy={position.y}
                      r={radius}
                      fill={color}
                      fillOpacity={isRoot ? 0.95 : 0.8}
                      stroke={isRoot ? "hsl(var(--foreground))" : "transparent"}
                      strokeWidth={isRoot ? 2 : 0}
                    />
                    <text
                      x={position.x}
                      y={position.y + radius + 11}
                      fontSize={isRoot ? 12 : 9.5}
                      textAnchor="middle"
                      fill="hsl(var(--foreground))"
                      fontWeight={isRoot ? 600 : 400}
                    >
                      {truncate(node.label, isRoot ? 26 : 18)}
                    </text>
                  </g>
                );
              })}
            </svg>
          </div>
        </CardContent>
      </Card>

      <div className="space-y-4">
        <Card>
          <CardHeader>
            <CardTitle>Selection</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-xs">
            {hovered ? (
              <>
                <div className="flex items-center gap-2">
                  <span
                    className="h-2.5 w-2.5 rounded-full"
                    style={{ background: TYPE_COLORS[hovered.type] ?? "gray" }}
                  />
                  <Badge variant="outline">{hovered.type.replace(/_/g, " ")}</Badge>
                </div>
                <p className="font-medium">{hovered.label}</p>
                <p className="font-mono text-[10px] text-muted-foreground">{hovered.key}</p>
                <div className="space-y-1 pt-1">
                  {Object.entries(hovered.properties ?? {}).slice(0, 8).map(([prop, value]) => (
                    <div key={prop} className="flex justify-between gap-2">
                      <span className="text-muted-foreground">{prop.replace(/_/g, " ")}</span>
                      <span className="max-w-[140px] truncate text-right">{String(value ?? "—")}</span>
                    </div>
                  ))}
                </div>
              </>
            ) : (
              <p className="text-muted-foreground">Hover a node to inspect its properties.</p>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Relationships</CardTitle>
          </CardHeader>
          <CardContent className="space-y-1.5 text-xs">
            {Object.entries(relationGroups).map(([relation, count]) => (
              <div key={relation} className="flex items-center justify-between">
                <span className="text-muted-foreground">{relation.replace(/_/g, " ")}</span>
                <span className="tabular-nums">{fmtNumber(count)}</span>
              </div>
            ))}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Legend</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-wrap gap-1.5">
            {Object.entries(TYPE_COLORS).map(([type, color]) => (
              <span key={type} className="inline-flex items-center gap-1 rounded-full border border-border/70 px-2 py-0.5 text-[10px]">
                <span className="h-2 w-2 rounded-full" style={{ background: color }} />
                {type.replace(/_/g, " ")}
              </span>
            ))}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function truncate(value: string, length: number): string {
  return value.length > length ? `${value.slice(0, length - 1)}…` : value;
}
