import { Plus } from "lucide-react";
import type { Metadata } from "next";
import { Suspense } from "react";
import { CarryLink, EmptyState, LoadingBlock, TimeAgo } from "@/components/common";
import { PageHeader } from "@/components/page-header";
import { buttonVariants } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { serverGet } from "@/lib/api";
import { FIELD_LABEL } from "@/lib/labels";
import { brandParam, type SP } from "@/lib/params";
import type { Claim, Field, Sku } from "@/lib/types";

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
  const claims = await Promise.all(skus.map((s) => serverGet<Claim[]>(`/skus/${s.id}/claims`)));

  return (
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
          {skus.map((s, i) => {
            const fields = new Set(claims[i].map((c) => c.field));
            fields.add("name");
            const last = claims[i].map((c) => c.created_at).sort().at(-1) ?? null;
            return (
              <TableRow key={s.id}>
                <TableCell>
                  <CarryLink href={`/products/${s.id}/truth`} className="font-medium hover:underline">
                    {s.name}
                  </CarryLink>
                  <div className="text-xs text-muted-foreground">{s.brand_name}</div>
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
  );
}
