"use client";

import * as React from "react";

/**
 * Lightweight inline sparkline. Rendered as a single SVG path so it stays cheap
 * when a dashboard renders dozens of KPI tiles at once.
 */
export function Sparkline({
  data,
  width = 96,
  height = 28,
  tone = "hsl(var(--primary))",
  fill = true,
  strokeWidth = 1.5,
  className,
}: {
  data: number[];
  width?: number;
  height?: number;
  tone?: string;
  fill?: boolean;
  strokeWidth?: number;
  className?: string;
}) {
  const gradId = React.useId();
  const hasData = data && data.length >= 2;

  const geometry = React.useMemo(() => {
    if (!hasData) return null;
    const min = Math.min(...data);
    const max = Math.max(...data);
    const span = max - min || 1;
    const stepX = width / (data.length - 1);
    const pad = 2;
    const points = data.map((value, index) => {
      const x = index * stepX;
      const y = height - pad - ((value - min) / span) * (height - pad * 2);
      return [x, y] as const;
    });
    const line = points
      .map(([x, y], i) => `${i === 0 ? "M" : "L"}${x.toFixed(2)},${y.toFixed(2)}`)
      .join(" ");
    return { line, area: `${line} L${width},${height} L0,${height} Z`, last: points[points.length - 1] };
  }, [data, hasData, width, height]);

  if (!geometry) return <div className={className} style={{ width, height }} aria-hidden />;

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      className={className}
      preserveAspectRatio="none"
      aria-hidden
    >
      <defs>
        <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={tone} stopOpacity="0.35" />
          <stop offset="100%" stopColor={tone} stopOpacity="0" />
        </linearGradient>
      </defs>
      {fill ? <path d={geometry.area} fill={`url(#${gradId})`} /> : null}
      <path
        d={geometry.line}
        fill="none"
        stroke={tone}
        strokeWidth={strokeWidth}
        strokeLinejoin="round"
        strokeLinecap="round"
      />
      <circle cx={geometry.last[0]} cy={geometry.last[1]} r={2} fill={tone} />
    </svg>
  );
}
