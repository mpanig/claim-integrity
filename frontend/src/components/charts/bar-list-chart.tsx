"use client";

import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { AXIS, ChartTooltip } from "./chart-tooltip";

/** Horizontal bars for one measure across categories (single series, so no legend). */
export function BarListChart({
  data,
  valueName,
  height,
  color = "var(--series-1)",
  unit = "",
  labelWidth = 170,
}: {
  data: { label: string; value: number }[];
  valueName: string;
  height?: number;
  color?: string;
  /** Appended to values in the tooltip, e.g. "%". */
  unit?: string;
  labelWidth?: number;
}) {
  const h = height ?? Math.max(120, data.length * 36 + 32);
  const format = (v: number | string) => `${v}${unit}`;
  return (
    <div style={{ height: h }} role="img" aria-label={`${valueName}: ${data.map((d) => `${d.label} ${d.value}`).join(", ")}`}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} layout="vertical" margin={{ top: 4, right: 16, bottom: 4, left: 0 }} barCategoryGap={8}>
          <CartesianGrid horizontal={false} stroke="var(--chart-grid)" />
          <XAxis type="number" allowDecimals={false} {...AXIS} />
          <YAxis type="category" dataKey="label" width={labelWidth} {...AXIS} axisLine={false} />
          <Tooltip cursor={{ fill: "var(--muted)", opacity: 0.6 }} content={<ChartTooltip format={format} />} />
          <Bar dataKey="value" name={valueName} fill={color} radius={[0, 4, 4, 0]} maxBarSize={16} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
