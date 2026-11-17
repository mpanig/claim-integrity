"use client";

import { Check, UserRound, X } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";
import { TimeAgo } from "@/components/common";
import { OwnerPicker } from "@/components/owner-picker";
import { SeverityBadge, StatusBadge, TruthBadge, VerdictBadge } from "@/components/status";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { useUrlState } from "@/hooks/use-url-state";
import { api } from "@/lib/api";
import { FIELD_LABEL, snippet } from "@/lib/labels";
import type { Conflict } from "@/lib/types";

type Bulk = { done: number; skipped: { id: number; reason: string }[] };

export function ConflictsTable({ conflicts }: { conflicts: Conflict[] }) {
  const router = useRouter();
  const { set } = useUrlState();
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [dialog, setDialog] = useState<"dismiss" | "assign" | null>(null);
  const [reason, setReason] = useState("");
  const [owner, setOwner] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // Drop selections that are no longer on screen (filters changed).
  const visible = new Set(conflicts.map((c) => c.id));
  const ids = [...selected].filter((id) => visible.has(id));
  const allChecked = ids.length > 0 && ids.length === conflicts.length;

  function toggle(id: number, on: boolean) {
    const next = new Set(selected);
    if (on) next.add(id);
    else next.delete(id);
    setSelected(next);
  }

  async function run(action: "accept" | "dismiss" | "assign") {
    setBusy(true);
    try {
      const r = await api<Bulk>("/conflicts/bulk", { method: "POST", body: { ids, action, reason, owner } });
      const verb = { accept: "Accepted", dismiss: "Dismissed", assign: "Assigned" }[action];
      toast.success(`${verb} ${r.done} conflict${r.done === 1 ? "" : "s"}`, {
        description: r.skipped.length
          ? `${r.skipped.length} skipped: ${r.skipped[0].reason}${r.skipped.length > 1 ? " (and others)" : ""}.`
          : undefined,
      });
      setSelected(new Set());
      setDialog(null);
      setReason("");
      router.refresh();
    } catch (e) {
      toast.error("Bulk action failed", { description: (e as Error).message });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col gap-3">
      {ids.length > 0 && (
        <div
          className="sticky top-16 z-20 flex flex-wrap items-center gap-2 rounded-xl border bg-background/95 p-2 shadow-sm backdrop-blur"
          role="toolbar"
          aria-label="Bulk actions"
        >
          <span className="px-2 text-sm font-medium">{ids.length} selected</span>
          <Button size="sm" disabled={busy} onClick={() => run("accept")}>
            <Check /> Accept
          </Button>
          <Button size="sm" variant="outline" disabled={busy} onClick={() => setDialog("assign")}>
            <UserRound /> Assign
          </Button>
          <Button size="sm" variant="outline" disabled={busy} onClick={() => setDialog("dismiss")}>
            <X /> Dismiss
          </Button>
          <Button size="sm" variant="ghost" className="ml-auto" onClick={() => setSelected(new Set())}>
            Clear selection
          </Button>
        </div>
      )}

      <div className="overflow-x-auto rounded-xl border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-8">
                <Checkbox
                  aria-label="Select all"
                  checked={allChecked}
                  indeterminate={ids.length > 0 && !allChecked}
                  onCheckedChange={(on) => setSelected(on ? new Set(conflicts.map((c) => c.id)) : new Set())}
                />
              </TableHead>
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
              <TableRow
                key={c.id}
                data-state={selected.has(c.id) ? "selected" : undefined}
                className="cursor-pointer"
                onClick={() => set({ conflict: String(c.id) }, "push")}
              >
                <TableCell onClick={(e) => e.stopPropagation()}>
                  <Checkbox
                    aria-label={`Select ${FIELD_LABEL[c.field]} on ${c.page_label}`}
                    checked={selected.has(c.id)}
                    onCheckedChange={(on) => toggle(c.id, !!on)}
                  />
                </TableCell>
                <TableCell>
                  <div className="flex flex-col items-start gap-1">
                    <div className="flex flex-wrap gap-1">
                      <VerdictBadge verdict={c.verdict} />
                      {c.truth_source === "inferred" && <TruthBadge status="inferred" />}
                    </div>
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

      <Dialog open={dialog !== null} onOpenChange={(o) => !o && setDialog(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              {dialog === "dismiss" ? "Dismiss" : "Assign"} {ids.length} conflict{ids.length === 1 ? "" : "s"}
            </DialogTitle>
            <DialogDescription>
              {dialog === "dismiss"
                ? "Only conflicts still “To review” can be dismissed; others are skipped."
                : "Sets the owner on every selected conflict."}
            </DialogDescription>
          </DialogHeader>
          {dialog === "dismiss" ? (
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="bulk-reason">Reason (required)</Label>
              <Textarea id="bulk-reason" value={reason} onChange={(e) => setReason(e.target.value)} />
            </div>
          ) : (
            <div className="flex flex-col gap-1.5">
              <Label>Owner</Label>
              <OwnerPicker value={owner} onChange={setOwner} />
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setDialog(null)}>
              Cancel
            </Button>
            <Button
              variant={dialog === "dismiss" ? "destructive" : "default"}
              disabled={busy || (dialog === "dismiss" && !reason.trim())}
              onClick={() => run(dialog!)}
            >
              {dialog === "dismiss" ? "Dismiss" : "Assign"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
