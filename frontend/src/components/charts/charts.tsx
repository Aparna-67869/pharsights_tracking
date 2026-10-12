"use client";

import * as React from "react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";

const AXIS = { stroke: "hsl(var(--muted-foreground))", fontSize: 11 };
const GRID = "hsl(var(--border))";
export const CHART_COLORS = [
  "hsl(217 91% 60%)",
  "hsl(199 89% 55%)",
  "hsl(142 69% 50%)",
  "hsl(38 92% 55%)",
  "hsl(280 65% 62%)",
  "hsl(340 75% 60%)",
  "hsl(170 70% 45%)",
  "hsl(20 85% 58%)",
];

function ChartFrame({
  title,
  subtitle,
  action,
  height = 260,
  children,
  className,
}: {
  title: string;
  subtitle?: string;
  action?: React.ReactNode;
  height?: number;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <Card className={cn("overflow-hidden", className)}>
      <CardHeader className="flex-row items-start justify-between">
        <div>
          <CardTitle>{title}</CardTitle>
          {subtitle ? <p className="mt-0.5 text-xs text-muted-foreground">{subtitle}</p> : null}
        </div>
        {action}
      </CardHeader>
      <CardContent>
        <div style={{ height }}>
          <ResponsiveContainer width="100%" height="100%">
            {children as React.ReactElement}
          </ResponsiveContainer>
        </div>
      </CardContent>
    </Card>
  );
}

const tooltipStyle = {
  contentStyle: {
    background: "hsl(var(--card))",
    border: "1px solid hsl(var(--border))",
    borderRadius: 8,
    fontSize: 12,
    color: "hsl(var(--card-foreground))",
  },
  labelStyle: { color: "hsl(var(--muted-foreground))", fontSize: 11 },
};

export function AreaTrend({
  title,
  subtitle,
  data,
  xKey,
  yKey,
  height,
  color = CHART_COLORS[0],
}: {
  title: string;
  subtitle?: string;
  data: Array<Record<string, string | number>>;
  xKey: string;
  yKey: string;
  height?: number;
  color?: string;
}) {
  return (
    <ChartFrame title={title} subtitle={subtitle} height={height}>
      <AreaChart data={data} margin={{ top: 8, right: 8, left: -18, bottom: 0 }}>
        <defs>
          <linearGradient id={`fill-${yKey}`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor={color} stopOpacity={0.35} />
            <stop offset="95%" stopColor={color} stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke={GRID} vertical={false} />
        <XAxis dataKey={xKey} tick={AXIS} tickLine={false} axisLine={false} minTickGap={24} />
        <YAxis tick={AXIS} tickLine={false} axisLine={false} width={44} />
        <Tooltip {...tooltipStyle} />
        <Area
          type="monotone"
          dataKey={yKey}
          stroke={color}
          strokeWidth={2}
          fill={`url(#fill-${yKey})`}
        />
      </AreaChart>
    </ChartFrame>
  );
}

export function BarSeries({
  title,
  subtitle,
  data,
  xKey,
  bars,
  height,
  layout = "horizontal",
  stacked,
}: {
  title: string;
  subtitle?: string;
  data: Array<Record<string, string | number>>;
  xKey: string;
  bars: Array<{ key: string; label: string; color?: string }>;
  height?: number;
  layout?: "horizontal" | "vertical";
  stacked?: boolean;
}) {
  const vertical = layout === "vertical";
  return (
    <ChartFrame title={title} subtitle={subtitle} height={height}>
      <BarChart
        data={data}
        layout={layout}
        margin={{ top: 8, right: 12, left: vertical ? 40 : -18, bottom: 0 }}
      >
        <CartesianGrid strokeDasharray="3 3" stroke={GRID} vertical={vertical} horizontal={!vertical} />
        {vertical ? (
          <>
            <XAxis type="number" tick={AXIS} tickLine={false} axisLine={false} />
            <YAxis
              type="category"
              dataKey={xKey}
              tick={AXIS}
              tickLine={false}
              axisLine={false}
              width={130}
            />
          </>
        ) : (
          <>
            <XAxis dataKey={xKey} tick={AXIS} tickLine={false} axisLine={false} minTickGap={16} />
            <YAxis tick={AXIS} tickLine={false} axisLine={false} width={44} />
          </>
        )}
        <Tooltip {...tooltipStyle} cursor={{ fill: "hsl(var(--muted) / 0.35)" }} />
        {bars.length > 1 ? <Legend wrapperStyle={{ fontSize: 11 }} /> : null}
        {bars.map((bar, index) => (
          <Bar
            key={bar.key}
            dataKey={bar.key}
            name={bar.label}
            stackId={stacked ? "stack" : undefined}
            fill={bar.color ?? CHART_COLORS[index % CHART_COLORS.length]}
            radius={vertical ? [0, 4, 4, 0] : [4, 4, 0, 0]}
            maxBarSize={vertical ? 18 : 36}
          />
        ))}
      </BarChart>
    </ChartFrame>
  );
}

export function LineSeries({
  title,
  subtitle,
  data,
  xKey,
  lines,
  height,
}: {
  title: string;
  subtitle?: string;
  data: Array<Record<string, string | number>>;
  xKey: string;
  lines: Array<{ key: string; label: string; color?: string }>;
  height?: number;
}) {
  return (
    <ChartFrame title={title} subtitle={subtitle} height={height}>
      <LineChart data={data} margin={{ top: 8, right: 12, left: -18, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke={GRID} vertical={false} />
        <XAxis dataKey={xKey} tick={AXIS} tickLine={false} axisLine={false} minTickGap={20} />
        <YAxis tick={AXIS} tickLine={false} axisLine={false} width={44} />
        <Tooltip {...tooltipStyle} />
        {lines.length > 1 ? <Legend wrapperStyle={{ fontSize: 11 }} /> : null}
        {lines.map((line, index) => (
          <Line
            key={line.key}
            type="monotone"
            dataKey={line.key}
            name={line.label}
            stroke={line.color ?? CHART_COLORS[index % CHART_COLORS.length]}
            strokeWidth={2}
            dot={false}
            activeDot={{ r: 4 }}
          />
        ))}
      </LineChart>
    </ChartFrame>
  );
}

export function DonutChart({
  title,
  subtitle,
  data,
  height,
}: {
  title: string;
  subtitle?: string;
  data: Array<{ name: string; value: number }>;
  height?: number;
}) {
  const total = data.reduce((sum, entry) => sum + (Number(entry.value) || 0), 0);
  if (data.length === 0 || total === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>{title}</CardTitle>
          {subtitle ? <p className="mt-0.5 text-xs text-muted-foreground">{subtitle}</p> : null}
        </CardHeader>
        <CardContent>
          <div className="grid h-[220px] place-items-center rounded-lg border border-dashed border-border">
            <p className="text-xs text-muted-foreground">No data recorded for this breakdown yet.</p>
          </div>
        </CardContent>
      </Card>
    );
  }
  return (
    <ChartFrame title={title} subtitle={subtitle} height={height}>
      <PieChart>
        <Tooltip {...tooltipStyle} />
        <Legend wrapperStyle={{ fontSize: 11 }} />
        <Pie
          data={data}
          dataKey="value"
          nameKey="name"
          innerRadius="55%"
          outerRadius="80%"
          paddingAngle={2}
          stroke="hsl(var(--card))"
          strokeWidth={2}
        >
          {data.map((entry, index) => (
            <Cell key={entry.name} fill={CHART_COLORS[index % CHART_COLORS.length]} />
          ))}
        </Pie>
      </PieChart>
    </ChartFrame>
  );
}

/** Generic heat grid rendered with plain CSS — no chart library needed. */
export function Heatmap({
  title,
  subtitle,
  cells,
  rowLabels,
  colLabels,
  getValue,
}: {
  title: string;
  subtitle?: string;
  cells: Array<{ row: string; col: string; value: number }>;
  rowLabels: string[];
  colLabels: string[];
  getValue: (row: string, col: string) => number;
}) {
  const max = Math.max(1, ...cells.map((cell) => cell.value));
  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        {subtitle ? <p className="mt-0.5 text-xs text-muted-foreground">{subtitle}</p> : null}
      </CardHeader>
      <CardContent>
        <div className="scrollbar-thin overflow-x-auto">
          <table className="border-separate border-spacing-1 text-[11px]">
            <thead>
              <tr>
                <th className="sticky left-0 bg-card px-2 text-left font-medium text-muted-foreground" />
                {colLabels.map((col) => (
                  <th key={col} className="px-1 pb-1 font-medium text-muted-foreground">
                    {col}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rowLabels.map((row) => (
                <tr key={row}>
                  <td className="sticky left-0 max-w-[150px] truncate bg-card px-2 text-left text-muted-foreground">
                    {row}
                  </td>
                  {colLabels.map((col) => {
                    const value = getValue(row, col);
                    const intensity = value / max;
                    return (
                      <td key={col} className="p-0">
                        <div
                          title={`${row} · ${col}: ${value}`}
                          className="grid h-7 w-10 place-items-center rounded text-[10px] font-medium tabular-nums"
                          style={{
                            background:
                              value === 0
                                ? "hsl(var(--muted) / 0.4)"
                                : `hsl(217 91% 60% / ${0.15 + intensity * 0.75})`,
                            color: intensity > 0.55 ? "white" : "hsl(var(--foreground))",
                          }}
                        >
                          {value || ""}
                        </div>
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  );
}
