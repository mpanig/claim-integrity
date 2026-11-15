"use client";

import { TimeAgo } from "@/components/common";
import { SeverityBadge, StatusBadge, VerdictBadge } from "@/components/status";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useUrlState } from "@/hooks/use-url-state";
import { FIELD_LABEL, snippet } from "@/lib/labels";
import type { Conflict } from "@/lib/types";

export function ConflictsTable({ conflicts }: { conflicts: Conflict[] }) {
  const { set } = useUrlState();
  return (
    <div className="overflow-x-auto rounded-xl border">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Issue</TableHead>
            <TableHead>Product</TableHead>
            <TableHead>Risk</TableHead>
            <TableHead>Status</TableHead>
            <TableHead>Owner</TableHead>
            <TableHead>Found</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {conflicts.map((c) => (
            <TableRow key={c.id} className="cursor-pointer" onClick={() => set({ conflict: String(c.id) }, "push")}>
              <TableCell>
                <div className="flex flex-col items-start gap-1">
                  <VerdictBadge verdict={c.verdict} />
                  <span className="text-sm font-medium">
                    {FIELD_LABEL[c.field]} on {c.page_label}
                  </span>
                  <span className="max-w-80 truncate text-xs text-muted-foreground">{snippet(c)}</span>
                </div>
              </TableCell>
              <TableCell className="max-w-64">
                <span className="block truncate">{c.sku_name}</span>
                <span className="text-xs text-muted-foreground">{c.brand_name}</span>
              </TableCell>
              <TableCell>
                <SeverityBadge severity={c.severity} />
              </TableCell>
              <TableCell>
                <StatusBadge status={c.status} />
              </TableCell>
              <TableCell className="text-muted-foreground">{c.owner ?? "Unassigned"}</TableCell>
              <TableCell className="text-muted-foreground">
                <TimeAgo iso={c.detected_at} />
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
