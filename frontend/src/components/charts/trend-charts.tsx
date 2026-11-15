"use client";

import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { Trends } from "@/lib/types";
import { AXIS, ChartTooltip } from "./chart-tooltip";

function weekLabel(iso: string) {
  return new Date(`${iso}T00:00:00Z`).toLocaleDateString("en-GB", { day: "numeric", month: "short", timeZone: "UTC" });
}

function LegendText(value: string) {
  return <span className="text-xs text-muted-foreground">{value}</span>;
}

export function ScoreTrendChart({ trends, brandColors }: { trends: Trends; brandColors: Record<string, string> }) {
  const multi = trends.brands.length > 1;
  const data = trends.weeks.map((w) => ({
    week: weekLabel(w.week),
    overall: w.score,
    ...Object.fromEntries(trends.brands.map((b) => [`b${b.id}`, w.brands[String(b.id)] ?? null])),
  }));
  return (
    <div className="h-64" role="img" aria-label="Consistency score by week">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 8, right: 16, bottom: 0, left: -12 }}>
          <CartesianGrid vertical={false} stroke="var(--chart-grid)" />
          <XAxis dataKey="week" {...AXIS} minTickGap={16} />
          <YAxis domain={[0, 100]} ticks={[0, 25, 50, 75, 100]} {...AXIS} axisLine={false} />
          <Tooltip cursor={{ stroke: "var(--chart-axis)", strokeDasharray: "3 3" }} content={<ChartTooltip />} />
          {multi && <Legend formatter={LegendText} iconType="plainline" />}
          {multi ? (
            trends.brands.map((b) => (
              <Line
                key={b.id}
                type="monotone"
                dataKey={`b${b.id}`}
                name={b.name}
                stroke={brandColors[String(b.id)]}
                strokeWidth={2}
                dot={false}
                activeDot={{ r: 4, strokeWidth: 2, stroke: "var(--card)" }}
                connectNulls
              />
            ))
          ) : (
            <Line
              type="monotone"
              dataKey="overall"
              name="Score"
              stroke="var(--series-1)"
              strokeWidth={2}
              dot={false}
              activeDot={{ r: 4, strokeWidth: 2, stroke: "var(--card)" }}
              connectNulls
            />
          )}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

export function OpenVsFixedChart({ trends }: { trends: Trends }) {
  const data = trends.weeks.map((w) => ({ week: weekLabel(w.week), open: w.unresolved, fixed: w.fixed }));
  return (
    <div className="h-64" role="img" aria-label="Open issues and verified fixes by week">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 8, right: 16, bottom: 0, left: -12 }}>
          <CartesianGrid vertical={false} stroke="var(--chart-grid)" />
          <XAxis dataKey="week" {...AXIS} minTickGap={16} />
          <YAxis allowDecimals={false} {...AXIS} axisLine={false} />
          <Tooltip cursor={{ stroke: "var(--chart-axis)", strokeDasharray: "3 3" }} content={<ChartTooltip />} />
          <Legend formatter={LegendText} iconType="plainline" />
          <Line type="monotone" dataKey="open" name="Open issues" stroke="var(--series-1)" strokeWidth={2} dot={false} connectNulls />
          <Line type="monotone" dataKey="fixed" name="Fixes verified that week" stroke="var(--series-2)" strokeWidth={2} dot={false} connectNulls />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
