import { ArrowUpRight, Gauge, Store, UsersRound } from "lucide-react";
import { CarryLink, ConflictLink, DemoBadge } from "@/components/common";
import { CreateTaskDialog } from "@/components/create-task-dialog";
import { SeverityBadge, Pill } from "@/components/status";
import { buttonVariants } from "@/components/ui/button";
import { easeLabel, OWNER_TYPE_ROLE, type Recommendation } from "@/lib/recommendations";

export function RecommendationCard({ r, rank }: { r: Recommendation; rank: number }) {
  return (
    <article className="flex flex-col gap-3 rounded-xl border bg-card p-4 text-card-foreground sm:flex-row sm:items-start">
      <span className="flex size-7 shrink-0 items-center justify-center rounded-full bg-muted text-xs font-semibold tabular-nums">
        {rank}
      </span>
      <div className="flex min-w-0 flex-1 flex-col gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <h3 className="font-medium">{r.title}</h3>
          {r.is_demo && <DemoBadge />}
          {r.state === "in_progress" && <Pill tone="serious">Task created</Pill>}
        </div>
        <p className="text-sm text-muted-foreground">{r.why}</p>
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 text-xs text-muted-foreground">
          <span className="flex items-center gap-1">
            <UsersRound className="size-3.5" /> {r.owner_label}
          </span>
          <span className="flex items-center gap-1">
            <Gauge className="size-3.5" /> {easeLabel(r.ease)}
          </span>
          {r.pages.length > 0 && (
            <span className="flex items-center gap-1">
              <Store className="size-3.5" /> {r.pages.join(", ")}
            </span>
          )}
          <span>
            {r.sku_name} · {r.brand_name}
          </span>
        </div>
      </div>
      <div className="flex shrink-0 flex-row flex-wrap items-center gap-2 sm:flex-col sm:items-end">
        {r.impact_points > 0 && (
          <span className="text-sm font-medium tabular-nums" title="Drift-score points this product loses once done">
            −{r.impact_points} drift
          </span>
        )}
        <SeverityBadge severity={r.severity} />
        {r.link ? (
          <CarryLink href={r.link} className={buttonVariants({ size: "sm", variant: "outline" })}>
            {r.action_label ?? "Open"} <ArrowUpRight />
          </CarryLink>
        ) : r.state === "todo" ? (
          <CreateTaskDialog
            title={r.title}
            conflictIds={r.conflict_ids}
            ownerHint={r.owner_label}
            suggestRole={OWNER_TYPE_ROLE[r.owner_type]}
          />
        ) : null}
        {r.conflict_ids.length > 0 && (
          <ConflictLink id={r.conflict_ids[0]} className="text-xs text-muted-foreground underline-offset-4 hover:underline">
            View {r.conflict_ids.length > 1 ? `${r.conflict_ids.length} issues` : "issue"}
          </ConflictLink>
        )}
      </div>
    </article>
  );
}
