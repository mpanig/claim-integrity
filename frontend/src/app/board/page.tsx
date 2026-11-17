import type { Metadata } from "next";
import { Suspense } from "react";
import { LoadingBlock } from "@/components/common";
import { ConflictFilters } from "@/components/conflict-filters";
import { FixBoard } from "@/components/fix-board";
import { PageHeader } from "@/components/page-header";
import { serverGet } from "@/lib/api";
import { brandParam, first, type SP } from "@/lib/params";
import type { ConflictPage } from "@/lib/types";

export const metadata: Metadata = { title: "Fix board" };

export default function BoardPage({ searchParams }: PageProps<"/board">) {
  return (
    <>
      <PageHeader
        title="Fix board"
        description="Track each issue from decision to verified fix, highest risk first. Drag a card to the next column, or use its button. Click a card for details, owner and due date."
      />
      <Suspense fallback={<LoadingBlock rows={2} />}>
        <Board searchParams={searchParams} />
      </Suspense>
    </>
  );
}

const OPEN = ["open", "accepted", "fixed"] as const;

async function Board({ searchParams }: { searchParams: Promise<SP> }) {
  const sp = await searchParams;
  const show = Math.min(200, Math.max(15, Number(first(sp.show) ?? 15) || 15));
  const filters = { brand_id: brandParam(sp), verdict: first(sp.verdict), min_severity: first(sp.sev) };
  // One page per column: open columns by highest risk first; verified = the 20 most recently verified.
  const [open, accepted, fixed, verified] = await Promise.all([
    ...OPEN.map((s) => serverGet<ConflictPage>("/conflicts/page", { ...filters, status: [s], limit: show })),
    serverGet<ConflictPage>("/conflicts/page", { ...filters, status: ["verified"], sort: "recent", limit: 20 }),
  ]);
  return (
    <div className="flex flex-col gap-4">
      <ConflictFilters board />
      <FixBoard
        columns={{ open, accepted, fixed, verified }}
        show={show}
      />
    </div>
  );
}
