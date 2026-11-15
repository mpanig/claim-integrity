import type { Metadata } from "next";
import { Suspense } from "react";
import { LoadingBlock } from "@/components/common";
import { FixBoard } from "@/components/fix-board";
import { PageHeader } from "@/components/page-header";
import { serverGet } from "@/lib/api";
import { brandParam, type SP } from "@/lib/params";
import type { Conflict } from "@/lib/types";

export const metadata: Metadata = { title: "Fix board" };

export default function BoardPage({ searchParams }: PageProps<"/board">) {
  return (
    <>
      <PageHeader
        title="Fix board"
        description="Track each issue from decision to verified fix. Drag a card to the next column, or use its button. Click a card for details, owner and due date."
      />
      <Suspense fallback={<LoadingBlock rows={2} />}>
        <Board searchParams={searchParams} />
      </Suspense>
    </>
  );
}

async function Board({ searchParams }: { searchParams: Promise<SP> }) {
  const sp = await searchParams;
  const conflicts = await serverGet<Conflict[]>("/conflicts", {
    brand_id: brandParam(sp),
    status: ["open", "accepted", "fixed", "verified"],
  });
  // Keep the verified column short: the 20 most recently verified.
  const verified = conflicts
    .filter((c) => c.status === "verified")
    .sort((a, b) => (b.status_changed_at ?? "").localeCompare(a.status_changed_at ?? ""))
    .slice(0, 20);
  return <FixBoard conflicts={[...conflicts.filter((c) => c.status !== "verified"), ...verified]} />;
}
