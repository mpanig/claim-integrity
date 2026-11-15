"use client";

import { CalendarClock, GripVertical, UserRound } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";
import { SeverityBadge, VerdictBadge } from "@/components/status";
import { Button } from "@/components/ui/button";
import { useUrlState } from "@/hooks/use-url-state";
import { api } from "@/lib/api";
import { shortDate } from "@/lib/format";
import { ACTION_LABEL, FIELD_LABEL, snippet, STATUS_LABEL } from "@/lib/labels";
import type { Conflict, Status } from "@/lib/types";
import { cn } from "@/lib/utils";
import { canMove, TRANSITIONS } from "@/lib/workflow";

const COLUMNS: { status: Status; hint: string }[] = [
  { status: "open", hint: "New issues waiting for a decision" },
  { status: "accepted", hint: "Agreed to fix; work in progress" },
  { status: "fixed", hint: "Fixed on the page; waiting for a re-check" },
  { status: "verified", hint: "Re-check confirmed the fix" },
];

function overdue(due: string | null) {
  return !!due && due < new Date().toISOString().slice(0, 10);
}

export function FixBoard({ conflicts }: { conflicts: Conflict[] }) {
  const router = useRouter();
  const { set } = useUrlState();
  const [dragging, setDragging] = useState<Conflict | null>(null);
  const [over, setOver] = useState<Status | null>(null);
  const [pending, setPending] = useState<number | null>(null);

  async function move(c: Conflict, to: Status) {
    if (!canMove(c.status, to)) {
      toast.error(`Can't move from "${STATUS_LABEL[c.status]}" to "${STATUS_LABEL[to]}"`, {
        description: "Issues move: To review → Accepted → Fixed → Verified.",
      });
      return;
    }
    setPending(c.id);
    try {
      await api(`/conflicts/${c.id}`, { method: "PATCH", body: { status: to } });
      toast.success(`Moved to "${STATUS_LABEL[to]}"`);
      router.refresh();
    } catch (e) {
      toast.error("Couldn't move it", { description: (e as Error).message });
    } finally {
      setPending(null);
    }
  }

  return (
    <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
      {COLUMNS.map(({ status, hint }) => {
        const items = conflicts.filter((c) => c.status === status);
        const droppable = dragging && canMove(dragging.status, status);
        return (
          <section
            key={status}
            aria-label={STATUS_LABEL[status]}
            onDragOver={(e) => {
              if (dragging) {
                e.preventDefault();
                setOver(status);
              }
            }}
            onDragLeave={() => setOver(null)}
            onDrop={(e) => {
              e.preventDefault();
              setOver(null);
              if (dragging && dragging.status !== status) move(dragging, status);
              setDragging(null);
            }}
            className={cn(
              "flex min-h-64 flex-col gap-3 rounded-xl border bg-muted/30 p-3 transition-colors",
              droppable && "border-dashed border-ring",
              over === status && droppable && "bg-muted",
            )}
          >
            <header>
              <h2 className="flex items-center justify-between text-sm font-medium">
                {STATUS_LABEL[status]}
                <span className="rounded-full bg-background px-2 text-xs tabular-nums ring-1 ring-border">{items.length}</span>
              </h2>
              <p className="text-xs text-muted-foreground">{hint}</p>
            </header>
            {items.length === 0 && <p className="py-6 text-center text-xs text-muted-foreground">Nothing here</p>}
            {items.map((c) => (
              <article
                key={c.id}
                draggable={TRANSITIONS[c.status].length > 0}
                onDragStart={() => setDragging(c)}
                onDragEnd={() => setDragging(null)}
                className={cn(
                  "flex flex-col gap-2 rounded-lg border bg-card p-3 text-card-foreground shadow-xs",
                  pending === c.id && "opacity-60",
                )}
              >
                <div className="flex items-start gap-1.5">
                  <VerdictBadge verdict={c.verdict} />
                  {TRANSITIONS[c.status].length > 0 && (
                    <GripVertical className="ml-auto size-4 cursor-grab text-muted-foreground" aria-hidden />
                  )}
                </div>
                <button
                  type="button"
                  className="text-left text-sm font-medium hover:underline"
                  onClick={() => set({ conflict: String(c.id) }, "push")}
                >
                  {FIELD_LABEL[c.field]} on {c.page_label}
                </button>
                <p className="text-xs text-muted-foreground">
                  {c.sku_name} · {c.brand_name}
                </p>
                <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
                  <span className="flex items-center gap-1">
                    <UserRound className="size-3.5" /> {c.owner ?? "Unassigned"}
                  </span>
                  {c.due_date && (
                    <span className={cn("flex items-center gap-1", overdue(c.due_date) && c.status !== "verified" && "font-medium text-foreground")}>
                      <CalendarClock className="size-3.5" />
                      {overdue(c.due_date) && c.status !== "verified" ? "Overdue · " : "Due "}
                      {shortDate(c.due_date)}
                    </span>
                  )}
                </div>
                <div className="flex flex-wrap items-center gap-1.5">
                  <SeverityBadge severity={c.severity} />
                  {TRANSITIONS[c.status]
                    .filter((s) => s !== "dismissed")
                    .map((to) => (
                      <Button key={to} size="xs" variant="outline" className="ml-auto" disabled={pending === c.id} onClick={() => move(c, to)}>
                        {to === "accepted" ? "Accept" : ACTION_LABEL[to]}
                      </Button>
                    ))}
                </div>
              </article>
            ))}
          </section>
        );
      })}
    </div>
  );
}
