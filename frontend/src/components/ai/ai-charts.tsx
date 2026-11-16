"use client";

import { Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { AXIS, ChartTooltip } from "@/components/charts/chart-tooltip";
import type { Insights } from "@/lib/ai";

// Ordinal ramp, one hue: rank 1 darkest. Unranked is neutral grey.
const RANK = [
  { key: "1", label: "#1", color: "#184f95" },
  { key: "2", label: "#2", color: "#256abf" },
  { key: "3", label: "#3", color: "#3987e5" },
  { key: "4", label: "#4", color: "#6da7ec" },
  { key: "5+", label: "#5 or lower", color: "#86b6ef" },
  { key: "unranked", label: "Mentioned, not ranked", color: "#c3c2b7" },
] as const;

function legendText(value: string) {
  return <span className="text-xs text-muted-foreground">{value}</span>;
}

export function RankChart({ rank }: { rank: Insights["rank"] }) {
  const data = rank.map((r) => ({ brand: r.brand, ...r.positions }));
  return (
    <div style={{ height: Math.max(160, data.length * 34 + 70) }} role="img" aria-label="Where each brand is ranked in AI answers">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} layout="vertical" margin={{ top: 4, right: 16, bottom: 4, left: 0 }} barCategoryGap={8}>
          <CartesianGrid horizontal={false} stroke="var(--chart-grid)" />
          <XAxis type="number" allowDecimals={false} {...AXIS} />
          <YAxis type="category" dataKey="brand" width={110} {...AXIS} axisLine={false} />
          <Tooltip cursor={{ fill: "var(--muted)", opacity: 0.6 }} content={<ChartTooltip />} />
          <Legend formatter={legendText} iconType="square" />
          {RANK.map((r) => (
            <Bar key={r.key} dataKey={r.key} name={r.label} stackId="rank" fill={r.color} stroke="var(--card)" strokeWidth={1} maxBarSize={18} />
          ))}
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

export function MentionTrend({ trend, brands, colors }: { trend: Insights["trend"]; brands: string[]; colors: Record<string, string> }) {
  const data = trend.map((t) => ({
    week: new Date(`${t.week}T00:00:00Z`).toLocaleDateString("en-GB", { day: "numeric", month: "short", timeZone: "UTC" }),
    ...Object.fromEntries(brands.map((b) => [b, typeof t[b] === "number" ? Math.round((t[b] as number) * 100) : null])),
  }));
  return (
    <div className="h-56" role="img" aria-label="Share of answers mentioning each of our brands, by week">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 8, right: 16, bottom: 0, left: -12 }}>
          <CartesianGrid vertical={false} stroke="var(--chart-grid)" />
          <XAxis dataKey="week" {...AXIS} minTickGap={16} />
          <YAxis domain={[0, 100]} unit="%" {...AXIS} axisLine={false} />
          <Tooltip content={<ChartTooltip format={(v) => `${v}%`} />} />
          {brands.length > 1 && <Legend formatter={legendText} iconType="plainline" />}
          {brands.map((b) => (
            <Line key={b} type="monotone" dataKey={b} name={b} stroke={colors[b]} strokeWidth={2} dot={false} connectNulls />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

/** AEO score (0-100) by week; rivals dashed. */
export function ScoreTrend({ trend, brands, colors, rivals = [] }: { trend: Record<string, string | number>[]; brands: string[]; colors: Record<string, string>; rivals?: string[] }) {
  const data = trend.map((t) => ({
    week: new Date(`${t.week}T00:00:00Z`).toLocaleDateString("en-GB", { day: "numeric", month: "short", timeZone: "UTC" }),
    ...Object.fromEntries(brands.map((b) => [b, typeof t[b] === "number" ? t[b] : null])),
  }));
  return (
    <div className="h-64" role="img" aria-label={`AEO score by week for ${brands.join(", ")}`}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 8, right: 16, bottom: 0, left: -12 }}>
          <CartesianGrid vertical={false} stroke="var(--chart-grid)" />
          <XAxis dataKey="week" {...AXIS} minTickGap={16} />
          <YAxis domain={[0, 100]} {...AXIS} axisLine={false} />
          <Tooltip content={<ChartTooltip />} />
          <Legend formatter={legendText} iconType="plainline" />
          {brands.map((b) => (
            <Line key={b} type="monotone" dataKey={b} name={b} stroke={colors[b]} strokeWidth={2} strokeDasharray={rivals.includes(b) ? "5 4" : undefined} dot={false} connectNulls />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
