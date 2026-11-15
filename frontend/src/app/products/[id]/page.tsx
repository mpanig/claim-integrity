import { ExternalLink, ShieldCheck } from "lucide-react";
import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { Suspense } from "react";
import { CarryLink, LoadingBlock, TimeAgo } from "@/components/common";
import { MatrixTable } from "@/components/matrix-table";
import { PageHeader } from "@/components/page-header";
import { RunCheckButton } from "@/components/run-check-button";
import { ScoreBadge } from "@/components/status";
import { buttonVariants } from "@/components/ui/button";
import { ApiError, serverGet } from "@/lib/api";
import type { Matrix } from "@/lib/types";

export const metadata: Metadata = { title: "Product" };

export default function ProductPage({ params }: PageProps<"/products/[id]">) {
  return (
    <Suspense fallback={<LoadingBlock rows={3} />}>
      <Product params={params} />
    </Suspense>
  );
}

async function Product({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  let m: Matrix;
  try {
    m = await serverGet<Matrix>(`/skus/${id}/matrix`);
  } catch (e) {
    if (e instanceof ApiError && (e.status === 404 || e.status === 422)) notFound();
    throw e;
  }
  const s = m.sku;
  return (
    <>
      <PageHeader
        title={s.name}
        description={
          <span className="flex flex-wrap items-center gap-x-2 gap-y-1">
            {s.brand_name}
            {s.line && <> · {s.line}</>} · {s.pages} page{s.pages === 1 ? "" : "s"} monitored · last checked{" "}
            <TimeAgo iso={s.last_checked_at} />
          </span>
        }
        actions={
          <>
            <ScoreBadge score={s.score} />
            <CarryLink href={`/products/${s.id}/truth`} className={buttonVariants({ variant: "outline" })}>
              <ShieldCheck /> Truth sheet
            </CarryLink>
            <RunCheckButton skuId={s.id} variant="default" />
          </>
        }
      />
      <section className="flex flex-col gap-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="font-medium">Claims across sources</h2>
            <p className="text-sm text-muted-foreground">
              Each row is a type of claim; each column a page. Click a highlighted cell to see the issue and act on it.
            </p>
          </div>
          <Legend />
        </div>
        {m.sources.length === 0 ? (
          <div className="rounded-xl border border-dashed p-8 text-center text-sm text-muted-foreground">
            No pages are monitored for this product yet. Pages appear here once they have been captured and read.
          </div>
        ) : (
          <MatrixTable matrix={m} />
        )}
        {m.truth.url && (
          <a
            href={m.truth.url}
            target="_blank"
            rel="noreferrer"
            className="inline-flex w-fit items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
          >
            Approved claims come from {m.truth.url} <ExternalLink className="size-3" />
          </a>
        )}
      </section>
    </>
  );
}

function Legend() {
  const items = [
    { cls: "bg-good/12 ring-good/30", label: "Matches" },
    { cls: "bg-warning/15 ring-warning/40", label: "Wording differs or missing" },
    { cls: "bg-critical/12 ring-critical/30", label: "Outdated, unapproved or contradictory" },
  ];
  return (
    <ul className="flex flex-wrap gap-3 text-xs text-muted-foreground">
      {items.map((i) => (
        <li key={i.label} className="flex items-center gap-1.5">
          <span className={`size-3 rounded-sm ring-1 ring-inset ${i.cls}`} />
          {i.label}
        </li>
      ))}
    </ul>
  );
}
