import type { Metadata } from "next";
import { Suspense } from "react";
import { EmptyState, LoadingBlock } from "@/components/common";
import { ConflictFilters } from "@/components/conflict-filters";
import { ConflictsTable } from "@/components/conflicts-table";
import { PageHeader } from "@/components/page-header";
import { serverGet } from "@/lib/api";
import { brandParam, first, type SP } from "@/lib/params";
import type { Conflict } from "@/lib/types";

export const metadata: Metadata = { title: "Conflicts" };

export default function ConflictsPage({ searchParams }: PageProps<"/conflicts">) {
  return (
    <>
      <PageHeader
        title="Conflicts"
        description="Every place a page disagrees with your approved claims. Filters are saved in the address bar, so you can share a view."
      />
      <Suspense fallback={<LoadingBlock rows={3} />}>
        <Conflicts searchParams={searchParams} />
      </Suspense>
    </>
  );
}

async function Conflicts({ searchParams }: { searchParams: Promise<SP> }) {
  const sp = await searchParams;
  const status = first(sp.status) ?? "unresolved";
  const [conflicts, everyone] = await Promise.all([
    serverGet<Conflict[]>("/conflicts", {
      brand_id: brandParam(sp),
      status: status === "unresolved" ? ["open", "accepted", "fixed"] : status === "any" ? undefined : [status],
      verdict: first(sp.verdict),
      owner: first(sp.owner),
    }),
    serverGet<Conflict[]>("/conflicts", { brand_id: brandParam(sp) }),
  ]);
  const owners = [...new Set(everyone.map((c) => c.owner).filter((o): o is string => !!o))].sort();

  return (
    <div className="flex flex-col gap-4">
      <ConflictFilters owners={owners} />
      <p className="text-sm text-muted-foreground">
        {conflicts.length} conflict{conflicts.length === 1 ? "" : "s"}
      </p>
      {conflicts.length ? (
        <ConflictsTable conflicts={conflicts} />
      ) : (
        <EmptyState title="No conflicts match these filters">Try another status or issue type.</EmptyState>
      )}
    </div>
  );
}
