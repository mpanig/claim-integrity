"use client";

/** Shared Recharts tooltip body: values in text ink, a colour swatch carries identity. */
export function ChartTooltip({
  active,
  payload,
  label,
  format = (v) => String(v),
}: {
  active?: boolean;
  payload?: { name?: string; value?: number | string; color?: string; dataKey?: string | number }[];
  label?: string | number;
  format?: (value: number | string, name?: string) => string;
}) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-lg border bg-popover px-3 py-2 text-xs text-popover-foreground shadow-md">
      {label !== undefined && <p className="mb-1 font-medium">{label}</p>}
      <ul className="flex flex-col gap-0.5">
        {payload.map((p) => (
          <li key={String(p.dataKey ?? p.name)} className="flex items-center gap-2">
            <span className="size-2 rounded-sm" style={{ background: p.color }} />
            <span className="text-muted-foreground">{p.name}</span>
            <span className="ml-auto pl-3 font-medium tabular-nums">{format(p.value ?? "", p.name)}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export const AXIS = {
  stroke: "var(--chart-axis)",
  tick: { fill: "var(--muted-foreground)", fontSize: 12 },
  tickLine: false,
  axisLine: { stroke: "var(--chart-grid)" },
} as const;
