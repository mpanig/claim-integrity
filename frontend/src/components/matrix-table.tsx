"use client";

import { CircleCheck, CircleMinus, OctagonAlert, TriangleAlert } from "lucide-react";
import { useUrlState } from "@/hooks/use-url-state";
import { FIELD_LABEL, SOURCE_TYPE_LABEL, VERDICT_LABEL } from "@/lib/labels";
import type { Matrix, MatrixCell } from "@/lib/types";
import { TruthBadge } from "@/components/status";
import { cn } from "@/lib/utils";

function summarise(value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  if (Array.isArray(value)) {
    if (value.length === 0) return "—";
    if (value.length > 4) return `${value.length} items: ${value.slice(0, 3).join(", ")}…`;
    return value.join(", ");
  }
  return String(value);
}

const STATE = {
  match: { cls: "bg-good/8 ring-good/25", icon: CircleCheck, iconCls: "text-good", label: "Matches" },
  warn: { cls: "bg-warning/12 ring-warning/40", icon: TriangleAlert, iconCls: "text-warning", label: "" },
  bad: { cls: "bg-critical/10 ring-critical/30", icon: OctagonAlert, iconCls: "text-critical", label: "" },
  na: { cls: "bg-transparent ring-border", icon: CircleMinus, iconCls: "text-muted-foreground", label: "Not applicable" },
} as const;

function Cell({ cell }: { cell: MatrixCell }) {
  const { set } = useUrlState();
  const st = STATE[cell.state];
  const open = cell.conflicts.filter((c) => c.status !== "dismissed");
  const top = open[0] ?? cell.conflicts[0];
  const label = cell.state === "warn" || cell.state === "bad" ? VERDICT_LABEL[top.verdict] : st.label;
  const extra = open.length > 1 ? ` +${open.length - 1} more` : "";
  const body = (
    <>
      <span className="flex items-center gap-1.5 text-xs font-medium">
        <st.icon className={cn("size-3.5 shrink-0", st.iconCls)} />
        {label}
        {extra && <span className="text-muted-foreground">{extra}</span>}
      </span>
      <span className="line-clamp-2 text-xs text-muted-foreground">{summarise(cell.value)}</span>
    </>
  );
  const cls = cn("flex h-full min-h-16 w-full flex-col gap-1 rounded-lg p-2 text-left ring-1 ring-inset", st.cls);
  if (!top) return <div className={cls}>{body}</div>;
  return (
    <button
      type="button"
      className={cn(cls, "transition-shadow hover:ring-2 focus-visible:ring-2 focus-visible:ring-ring")}
      onClick={() => set({ conflict: String(top.id) }, "push")}
      aria-label={`${label}: open details`}
    >
      {body}
    </button>
  );
}

export function MatrixTable({ matrix }: { matrix: Matrix }) {
  return (
    <div className="overflow-x-auto rounded-xl border">
      <table className="w-full min-w-[720px] border-separate border-spacing-2 text-sm">
        <thead>
          <tr>
            <th className="w-40 text-left text-xs font-medium text-muted-foreground" scope="col">
              Claim
            </th>
            <th className="min-w-48 text-left align-bottom" scope="col">
              {matrix.truth.status === "approved" ? (
                <>
                  <span className="block text-sm font-medium">Brand site</span>
                  <span className="block text-xs font-normal text-muted-foreground">Approved truth</span>
                </>
              ) : (
                <>
                  <span className="block text-sm font-medium">No truth sheet</span>
                  <TruthBadge status={matrix.truth.status} method={matrix.truth.method} className="mt-1" />
                </>
              )}
            </th>
            {matrix.sources.map((s) => (
              <th key={s.page_id} className="min-w-48 text-left align-bottom" scope="col">
                <a href={s.url} target="_blank" rel="noreferrer" className="block text-sm font-medium hover:underline">
                  {s.label}
                </a>
                <span className="block text-xs font-normal text-muted-foreground">
                  {SOURCE_TYPE_LABEL[s.source_type] ?? s.source_type}
                  {s.weight !== 1 && ` · weight ${s.weight}`}
                </span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {matrix.fields.map((f) => (
            <tr key={f}>
              <th scope="row" className="text-left align-top text-sm font-medium">
                {FIELD_LABEL[f]}
              </th>
              <td className="align-top">
                <div className={matrix.truth.status === "approved" ? "flex min-h-16 flex-col gap-1 rounded-lg bg-muted/50 p-2" : "flex min-h-16 flex-col gap-1 rounded-lg border border-dashed border-warning/60 bg-warning/5 p-2"}>
                  <span className="text-xs font-medium">
                    {matrix.truth.status === "approved"
                      ? "Approved"
                      : matrix.truth.agreement[f] !== undefined
                        ? `Inferred · ${Math.round((matrix.truth.agreement[f] ?? 0) * 100)}% of page weight agrees`
                        : "Inferred"}
                  </span>
                  <span className="line-clamp-2 text-xs text-muted-foreground">{summarise(matrix.truth.values[f])}</span>
                </div>
              </td>
              {matrix.sources.map((s) => (
                <td key={s.page_id} className="align-top">
                  <Cell cell={s.cells[f]} />
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
