"use client";

import { CheckCheck, OctagonAlert, TrendingDown } from "lucide-react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { CarryLink, TimeAgo } from "@/components/common";
import { Button } from "@/components/ui/button";
import { useUrlState } from "@/hooks/use-url-state";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

export interface AlertItem {
  id: number;
  kind: "high_risk" | "score_drop";
  title: string;
  body: string;
  sku_id: number;
  sku_name: string;
  conflict_id: number | null;
  created_at: string;
  read: boolean;
}

export function AlertsList({ items, unread }: { items: AlertItem[]; unread: number }) {
  const router = useRouter();
  const { set, params } = useUrlState();

  async function markRead(id: number, read: boolean) {
    try {
      await api(`/alerts/${id}/read`, { method: "POST", params: { read } });
      router.refresh();
      window.dispatchEvent(new Event("alerts-changed"));
    } catch (e) {
      toast.error("Couldn't update the alert", { description: (e as Error).message });
    }
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center justify-between gap-2">
        <p className="text-sm text-muted-foreground">
          {unread} unread of {items.length}
        </p>
        <Button
          variant="outline"
          size="sm"
          disabled={unread === 0}
          onClick={async () => {
            await api("/alerts/read-all", { method: "POST", params: { brand_id: params.get("brand") } });
            toast.success("All alerts marked as read");
            router.refresh();
            window.dispatchEvent(new Event("alerts-changed"));
          }}
        >
          <CheckCheck /> Mark all read
        </Button>
      </div>
      <ul className="flex flex-col divide-y rounded-xl border">
        {items.map((a) => {
          const Icon = a.kind === "score_drop" ? TrendingDown : OctagonAlert;
          return (
            <li key={a.id} className={cn("flex items-start gap-3 p-4", !a.read && "bg-muted/40")}>
              <span className="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-full bg-critical/10">
                <Icon className="size-4 text-critical" />
              </span>
              <div className="min-w-0 flex-1">
                <p className="flex items-center gap-2 text-sm font-medium">
                  {!a.read && <span className="size-2 rounded-full bg-series-1" aria-label="Unread" />}
                  {a.title}
                </p>
                <p className="text-sm text-muted-foreground">{a.body}</p>
                <div className="mt-1 flex flex-wrap items-center gap-x-3 text-xs text-muted-foreground">
                  <TimeAgo iso={a.created_at} />
                  <CarryLink href={`/products/${a.sku_id}`} className="hover:text-foreground hover:underline">
                    {a.sku_name}
                  </CarryLink>
                </div>
              </div>
              <div className="flex shrink-0 flex-col items-end gap-1.5 sm:flex-row sm:items-center">
                {a.conflict_id && (
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => {
                      if (!a.read) markRead(a.id, true);
                      set({ conflict: String(a.conflict_id) }, "push");
                    }}
                  >
                    Review
                  </Button>
                )}
                <Button size="sm" variant="ghost" onClick={() => markRead(a.id, !a.read)}>
                  Mark {a.read ? "unread" : "read"}
                </Button>
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
