"use client";

import * as React from "react";
import {
  forceCenter,
  forceCollide,
  forceLink,
  forceManyBody,
  forceSimulation,
  type Simulation,
  type SimulationLinkDatum,
  type SimulationNodeDatum,
} from "d3-force";
import { cn } from "@/lib/utils";
import type { GraphNeighborhood, GraphNode } from "@/types/api";

export const TYPE_COLORS: Record<string, string> = {
  drug: "#3B82F6",
  nda: "#22D3EE",
  anda: "#10B981",
  patent: "#A855F7",
  ftf_record: "#F59E0B",
  pte_application: "#FB923C",
  pte_certificate: "#F472B6",
  active_moiety: "#2DD4BF",
  sponsor: "#EAB308",
  orange_book_record: "#EF4444",
};

export function colorFor(type: string): string {
  return TYPE_COLORS[type] ?? "#94A3B8";
}

interface SimNode extends SimulationNodeDatum {
  id: string;
  data: GraphNode;
  radius: number;
}
interface SimLink extends SimulationLinkDatum<SimNode> {
  id: string;
  relation: string;
}

/**
 * Force-directed graph explorer. d3-force computes the layout in a fixed
 * coordinate space; the SVG viewBox is panned/zoomed via a transform, and a
 * native wheel listener scales about the pointer so zoom stays centred.
 *
 * Interactions: hover highlights a node and its edges, click selects a node for
 * the details panel, background drag pans, wheel zooms.
 */
export function ForceGraph({
  data,
  selectedId,
  onSelect,
  height = 560,
}: {
  data: GraphNeighborhood;
  selectedId: string | null;
  onSelect: (node: GraphNode | null) => void;
  height?: number;
}) {
  const width = 1000;
  const [nodes, setNodes] = React.useState<SimNode[]>([]);
  const [links, setLinks] = React.useState<SimLink[]>([]);
  const [hovered, setHovered] = React.useState<string | null>(null);
  const [transform, setTransform] = React.useState({ x: 0, y: 0, k: 1 });
  const [drag, setDrag] = React.useState<{ x: number; y: number; tx: number; ty: number } | null>(null);

  // Build the simulation whenever the neighbourhood changes.
  React.useEffect(() => {
    const simNodes: SimNode[] = data.nodes.map((node) => ({
      id: node.id,
      data: node,
      radius: node.id === data.root.id ? 16 : 6 + Math.min(node.importance, 100) / 12,
      x: width / 2 + (Math.random() - 0.5) * 200,
      y: height / 2 + (Math.random() - 0.5) * 200,
    }));
    const byId = new Map(simNodes.map((node) => [node.id, node]));
    const simLinks: SimLink[] = data.edges
      .filter((edge) => byId.has(edge.source) && byId.has(edge.target))
      .map((edge) => ({ id: edge.id, relation: edge.relation, source: edge.source, target: edge.target }));

    const simulation: Simulation<SimNode, SimLink> = forceSimulation(simNodes)
      .force("charge", forceManyBody().strength(-260))
      .force("center", forceCenter(width / 2, height / 2))
      .force("collide", forceCollide<SimNode>().radius((node) => node.radius + 12))
      .force(
        "link",
        forceLink<SimNode, SimLink>(simLinks)
          .id((node) => node.id)
          .distance(120)
          .strength(0.4),
      );

    simulation.on("tick", () => {
      setNodes([...simNodes]);
      setLinks([...simLinks]);
    });

    return () => {
      simulation.stop();
    };
  }, [data, height]);

  const nodeById = React.useMemo(() => new Map(nodes.map((node) => [node.id, node])), [nodes]);
  const activeId = hovered ?? selectedId;

  const panned = drag
    ? { x: drag.tx + (drag.x - 0), y: drag.ty, k: transform.k }
    : transform;

  return (
    <div
      className="relative overflow-hidden rounded-lg border border-border/70 bg-[radial-gradient(circle_at_50%_40%,hsl(var(--primary)/0.06),transparent_60%)]"
      style={{ height }}
      onMouseLeave={() => setDrag(null)}
      onMouseMove={(event) => {
        if (!drag) return;
        setTransform((prev) => ({ ...prev, x: drag.tx + (event.clientX - drag.x), y: drag.ty + (event.clientY - drag.y) }));
      }}
      onMouseUp={() => setDrag(null)}
    >
      <svg
        className="h-full w-full cursor-grab active:cursor-grabbing"
        onWheel={(event) => {
          event.preventDefault();
          const rect = (event.currentTarget as SVGSVGElement).getBoundingClientRect();
          const px = event.clientX - rect.left;
          const py = event.clientY - rect.top;
          setTransform((prev) => {
            const nextK = Math.min(3, Math.max(0.35, prev.k * (event.deltaY < 0 ? 1.12 : 0.89)));
            const ratio = nextK / prev.k;
            return { k: nextK, x: px - (px - prev.x) * ratio, y: py - (py - prev.y) * ratio };
          });
        }}
        onMouseDown={(event) => {
          if (event.button !== 0) return;
          setDrag({ x: event.clientX, y: event.clientY, tx: transform.x, ty: transform.y });
        }}
        onClick={(event) => {
          if (event.target === event.currentTarget) onSelect(null);
        }}
      >
        <g transform={`translate(${panned.x},${panned.y}) scale(${panned.k})`}>
          {links.map((link) => {
            const s = typeof link.source === "object" ? (link.source as SimNode) : nodeById.get(String(link.source));
            const t = typeof link.target === "object" ? (link.target as SimNode) : nodeById.get(String(link.target));
            if (!s || !t) return null;
            const active = activeId && (s.id === activeId || t.id === activeId);
            return (
              <line
                key={link.id}
                x1={s.x}
                y1={s.y}
                x2={t.x}
                y2={t.y}
                stroke={active ? "hsl(var(--primary))" : "hsl(var(--muted-foreground))"}
                strokeOpacity={active ? 0.85 : 0.16}
                strokeWidth={active ? 1.6 / panned.k : 1 / panned.k}
              />
            );
          })}

          {nodes.map((node) => {
            const active = activeId === node.id;
            const dim = activeId && !active;
            const color = colorFor(node.data.type);
            const isRoot = node.data.id === data.root.id;
            return (
              <g
                key={node.id}
                transform={`translate(${node.x},${node.y})`}
                className="cursor-pointer"
                opacity={dim ? 0.35 : 1}
                onMouseEnter={() => setHovered(node.id)}
                onMouseLeave={() => setHovered(null)}
                onClick={(event) => {
                  event.stopPropagation();
                  onSelect(node.data);
                }}
              >
                {isRoot ? <circle r={node.radius + 6} fill={color} fillOpacity={0.14} /> : null}
                <circle
                  r={node.radius}
                  fill={color}
                  fillOpacity={0.85}
                  stroke={active ? "hsl(var(--foreground))" : "transparent"}
                  strokeWidth={active ? 1.5 / panned.k : 0}
                />
                <text
                  y={node.radius + 11}
                  textAnchor="middle"
                  fontSize={(isRoot ? 12 : 9.5) / panned.k}
                  fill="hsl(var(--foreground))"
                  fontWeight={isRoot ? 600 : 400}
                  style={{ pointerEvents: "none" }}
                >
                  {truncate(node.data.label, isRoot ? 26 : 18)}
                </text>
              </g>
            );
          })}
        </g>
      </svg>

      <div className="pointer-events-none absolute bottom-2 left-2 flex flex-wrap gap-1.5">
        {Object.entries(TYPE_COLORS).map(([type, color]) => (
          <span
            key={type}
            className="inline-flex items-center gap-1 rounded-full border border-border/60 bg-panel/80 px-2 py-0.5 text-[9px] text-muted-foreground backdrop-blur"
          >
            <span className="h-1.5 w-1.5 rounded-full" style={{ background: color }} />
            {type.replace(/_/g, " ")}
          </span>
        ))}
      </div>
      <div className="pointer-events-none absolute right-2 top-2 rounded-md border border-border/60 bg-panel/80 px-2 py-1 text-[10px] text-muted-foreground backdrop-blur">
        {data.nodes.length} nodes · {data.edges.length} edges · zoom {transform.k.toFixed(2)}×
      </div>
    </div>
  );
}

function truncate(value: string, length: number): string {
  return value.length > length ? `${value.slice(0, length - 1)}…` : value;
}

export { cn };
