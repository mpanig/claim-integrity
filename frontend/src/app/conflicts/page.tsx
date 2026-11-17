import type { Metadata } from "next";
import { Suspense } from "react";
import { EmptyState, LoadingBlock } from "@/components/common";
import { ConflictFilters } from "@/components/conflict-filters";
import { ConflictsTable } from "@/components/conflicts-table";
import { Pager } from "@/components/pager";
import { PageHeader } from "@/components/page-header";
import { serverGet } from "@/lib/api";
import { brandParam, first, type SP } from "@/lib/params";
import type { ConflictPage } from "@/lib/types";

const PAGE_SIZE = 50;

export const metadata: Metadata = { title: "Conflicts" };

export default function ConflictsPage({ searchParams }: PageProps<"/conflicts">) {
  return (
    <>
      <PageHeader
        title="Conflicts"
        description="Every place a page disagrees with its truth, highest risk first, 50 per page. Filters are saved in the address bar, so you can share a view."
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
  const page = Math.max(1, Number(first(sp.p) ?? 1) || 1);
  const data = await serverGet<ConflictPage>("/conflicts/page", {
    brand_id: brandParam(sp),
    status: status === "unresolved" ? ["open", "accepted", "fixed"] : status === "any" ? undefined : [status],
    verdict: first(sp.verdict),
    owner: first(sp.owner),
    min_severity: first(sp.sev),
    limit: PAGE_SIZE,
    offset: (page - 1) * PAGE_SIZE,
  });

  return (
    <div className="flex flex-col gap-4">
      <ConflictFilters owners={data.owners} />
      <Pager total={data.total} limit={data.limit} offset={data.offset} />
      {data.items.length ? (
        <>
          <ConflictsTable conflicts={data.items} />
          {data.total > data.limit && <Pager total={data.total} limit={data.limit} offset={data.offset} />}
        </>
      ) : (
        <EmptyState title="No conflicts match these filters">Try another status, risk level or issue type.</EmptyState>
      )}
    </div>
  );
}
