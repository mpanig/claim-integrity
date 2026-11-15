import { Plus } from "lucide-react";
import type { Metadata } from "next";
import { Suspense } from "react";
import { CarryLink, EmptyState, LoadingBlock, TimeAgo } from "@/components/common";
import { PageHeader } from "@/components/page-header";
import { RunCheckButton } from "@/components/run-check-button";
import { SearchBox } from "@/components/search-box";
import { ScoreBadge } from "@/components/status";
import { buttonVariants } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { serverGet } from "@/lib/api";
import { brandParam, first, type SP } from "@/lib/params";
import type { Sku } from "@/lib/types";

export const metadata: Metadata = { title: "Products" };

export default function ProductsPage({ searchParams }: PageProps<"/products">) {
  return (
    <>
      <PageHeader
        title="Products"
        description="Every product you monitor, with its consistency score across the pages that sell it."
        actions={
          <CarryLink href="/products/new" className={buttonVariants()}>
            <Plus /> Add product
          </CarryLink>
        }
      />
      <Suspense fallback={null}>
        <SearchBox placeholder="Search by product, brand or GTIN" />
      </Suspense>
      <Suspense fallback={<LoadingBlock rows={2} />}>
        <ProductTable searchParams={searchParams} />
      </Suspense>
    </>
  );
}

async function ProductTable({ searchParams }: { searchParams: Promise<SP> }) {
  const sp = await searchParams;
  const q = first(sp.q);
  const skus = await serverGet<Sku[]>("/skus", { brand_id: brandParam(sp), q });

  if (skus.length === 0) {
    return (
      <EmptyState title={q ? `No products match “${q}”` : "No products yet"}>
        {q ? "Try a different search or brand." : "Add a product and its approved claims to start monitoring."}
      </EmptyState>
    );
  }

  return (
    <div className="overflow-x-auto rounded-xl border">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Product</TableHead>
            <TableHead>Score</TableHead>
            <TableHead className="text-right">Open issues</TableHead>
            <TableHead className="text-right">Pages</TableHead>
            <TableHead>Last checked</TableHead>
            <TableHead className="w-0" />
          </TableRow>
        </TableHeader>
        <TableBody>
          {skus.map((s) => (
            <TableRow key={s.id}>
              <TableCell className="max-w-[22rem]">
                <CarryLink href={`/products/${s.id}`} className="block truncate font-medium hover:underline">
                  {s.name}
                </CarryLink>
                <span className="text-xs text-muted-foreground">
                  {s.brand_name}
                  {s.line && ` · ${s.line}`}
                  {s.gtin && ` · GTIN ${s.gtin}`}
                </span>
              </TableCell>
              <TableCell>
                <ScoreBadge score={s.score} />
              </TableCell>
              <TableCell className="text-right tabular-nums">{s.unresolved}</TableCell>
              <TableCell className="text-right tabular-nums">{s.pages}</TableCell>
              <TableCell className="text-muted-foreground">
                <TimeAgo iso={s.last_checked_at} />
              </TableCell>
              <TableCell>
                <RunCheckButton skuId={s.id} size="sm" />
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
