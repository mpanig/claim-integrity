import { Plus, ShieldCheck, TriangleAlert } from "lucide-react";
import type { Metadata } from "next";
import { Suspense } from "react";
import { CarryLink, EmptyState, LoadingBlock, TimeAgo } from "@/components/common";
import { PageHeader } from "@/components/page-header";
import { TruthBadge } from "@/components/status";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { buttonVariants } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { serverGet } from "@/lib/api";
import { FIELD_LABEL } from "@/lib/labels";
import { brandParam, type SP } from "@/lib/params";
import type { Field, Sku } from "@/lib/types";

export const metadata: Metadata = { title: "Truth sheets" };

const FIELDS: Field[] = ["name", "ingredients", "free_from", "claims", "seals"];

export default function TruthSheetsPage({ searchParams }: PageProps<"/truth-sheets">) {
  return (
    <>
      <PageHeader
        title="Truth sheets"
        description="The approved claims for each product. Every retailer and site is checked against these."
        actions={
          <CarryLink href="/products/new" className={buttonVariants()}>
            <Plus /> Add product
          </CarryLink>
        }
      />
      <Suspense fallback={<LoadingBlock rows={2} />}>
        <Sheets searchParams={searchParams} />
      </Suspense>
    </>
  );
}

async function Sheets({ searchParams }: { searchParams: Promise<SP> }) {
  const sp = await searchParams;
  const skus = await serverGet<Sku[]>("/skus", { brand_id: brandParam(sp) });
  if (!skus.length) return <EmptyState title="No truth sheets yet">Add a product to create its truth sheet.</EmptyState>;
  const summary = await serverGet<{ sku_id: number; fields: Field[]; last_approved: string | null }[]>("/truth-sheets", { brand_id: brandParam(sp) });
  const bySku = new Map(summary.map((r) => [r.sku_id, r]));
  const missing = skus.filter((s) => s.truth_status !== "approved");

  return (
    <div className="flex flex-col gap-4">
      {missing.length > 0 && (
        <Alert>
          <TriangleAlert />
          <AlertTitle>
            {missing.length} product{missing.length === 1 ? " has" : "s have"} no truth sheet
          </AlertTitle>
          <AlertDescription className="flex flex-col gap-2">
            <span>
              They are checked against an inferred truth (what their pages agree on), which is unverified. Review and approve
              each one; its drift score is recomputed straight away.
            </span>
            <ul className="flex flex-col gap-1.5">
              {missing.map((s) => (
                <li key={s.id} className="flex flex-wrap items-center gap-2">
                  <span className="font-medium text-foreground">Add a truth sheet for {s.name}</span>
                  <CarryLink href={`/products/${s.id}/truth?prefill=inferred`} className={buttonVariants({ size: "sm", variant: "outline" })}>
                    <ShieldCheck /> {s.truth_status === "inferred" ? "Review inferred truth sheet" : "Add truth sheet"}
                  </CarryLink>
                </li>
              ))}
            </ul>
          </AlertDescription>
        </Alert>
      )}
    <div className="overflow-x-auto rounded-xl border">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Product</TableHead>
            <TableHead>Approved</TableHead>
            <TableHead>Last approved</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {skus.map((s) => {
            const fields = new Set<Field>(bySku.get(s.id)?.fields ?? []);
            if (s.truth_status === "approved") fields.add("name");
            const last = bySku.get(s.id)?.last_approved ?? null;
            return (
              <TableRow key={s.id}>
                <TableCell>
                  <CarryLink href={`/products/${s.id}/truth`} className="font-medium hover:underline">
                    {s.name}
                  </CarryLink>
                  <div className="text-xs text-muted-foreground">{s.brand_name}</div>
                  <TruthBadge status={s.truth_status} method={s.inferred_method} className="mt-1" />
                </TableCell>
                <TableCell>
                  <ul className="flex flex-wrap gap-1.5">
                    {FIELDS.map((f) => (
                      <li
                        key={f}
                        className={
                          fields.has(f)
                            ? "rounded-md border px-1.5 py-0.5 text-xs"
                            : "rounded-md border border-dashed px-1.5 py-0.5 text-xs text-muted-foreground"
                        }
                      >
                        {FIELD_LABEL[f]}
                        {!fields.has(f) && " · not set"}
                      </li>
                    ))}
                  </ul>
                </TableCell>
                <TableCell className="text-muted-foreground">
                  <TimeAgo iso={last} />
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </div>
    </div>
  );
}
