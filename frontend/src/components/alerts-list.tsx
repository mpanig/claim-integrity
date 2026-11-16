"use client";

import { ArrowUpRight, Bot, CheckCheck, OctagonAlert, ThumbsDown, TrendingDown, Users } from "lucide-react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { CarryLink, DemoBadge, TimeAgo } from "@/components/common";
import { Button } from "@/components/ui/button";
import { useUrlState } from "@/hooks/use-url-state";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

export interface AlertItem {
  id: number;
  kind: "high_risk" | "score_drop" | "aeo_score_drop" | "aeo_lost_recommendation" | "aeo_wrong_fact" | "aeo_overtaken";
  title: string;
  body: string;
  sku_id: number | null;
  sku_name: string | null;
  brand_name: string | null;
  link: string | null;
  is_demo: boolean;
  conflict_id: number | null;
  created_at: string;
  read: boolean;
}

const ICON = {
  high_risk: OctagonAlert,
  score_drop: TrendingDown,
  aeo_score_drop: TrendingDown,
  aeo_overtaken: Users,
  aeo_lost_recommendation: ThumbsDown,
  aeo_wrong_fact: Bot,
} as const;

export function AlertsList({ items, unread, kindPrefix }: { items: AlertItem[]; unread: number; kindPrefix?: string }) {
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
            await api("/alerts/read-all", { method: "POST", params: { brand_id: params.get("brand"), kind_prefix: kindPrefix } });
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
          const Icon = ICON[a.kind] ?? OctagonAlert;
          return (
            <li key={a.id} className={cn("flex items-start gap-3 p-4", !a.read && "bg-muted/40")}>
              <span className="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-full bg-critical/10">
                <Icon className="size-4 text-critical" />
              </span>
              <div className="min-w-0 flex-1">
                <p className="flex items-center gap-2 text-sm font-medium">
                  {!a.read && <span className="size-2 rounded-full bg-series-1" aria-label="Unread" />}
                  <span>{a.title}</span>
                  {a.is_demo && <DemoBadge className="shrink-0" />}
                </p>
                <p className="text-sm text-muted-foreground">{a.body}</p>
                <div className="mt-1 flex flex-wrap items-center gap-x-3 text-xs text-muted-foreground">
                  <TimeAgo iso={a.created_at} />
                  {a.sku_id ? (
                    <CarryLink href={`/products/${a.sku_id}`} className="hover:text-foreground hover:underline">
                      {a.sku_name}
                    </CarryLink>
                  ) : (
                    a.brand_name && <span>{a.brand_name} · AEO / GEO</span>
                  )}
                </div>
              </div>
              <div className="flex shrink-0 flex-col items-end gap-1.5 sm:flex-row sm:items-center">
                {a.link && !a.conflict_id && (
                  <Button size="sm" variant="outline" nativeButton={false} render={<CarryLink href={a.link} />} onClick={() => !a.read && markRead(a.id, true)}>
                    Open <ArrowUpRight />
                  </Button>
                )}
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
