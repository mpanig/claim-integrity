import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { Suspense } from "react";
import { CarryLink, LoadingBlock } from "@/components/common";
import { PageHeader } from "@/components/page-header";
import { TruthSheetForm } from "@/components/truth-sheet-form";
import { ApiError, serverGet } from "@/lib/api";
import type { Claim, InferredTruth, Sku } from "@/lib/types";

export const metadata: Metadata = { title: "Truth sheet" };

export default function TruthPage({ params }: PageProps<"/products/[id]/truth">) {
  return (
    <Suspense fallback={<LoadingBlock rows={3} />}>
      <Truth params={params} />
    </Suspense>
  );
}

async function Truth({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  let sku: Sku, claims: Claim[], inferred: InferredTruth;
  try {
    [sku, claims, inferred] = await Promise.all([
      serverGet<Sku>(`/skus/${id}`),
      serverGet<Claim[]>(`/skus/${id}/claims`),
      serverGet<InferredTruth>(`/skus/${id}/inferred-truth`),
    ]);
  } catch (e) {
    if (e instanceof ApiError && (e.status === 404 || e.status === 422)) notFound();
    throw e;
  }
  return (
    <>
      <PageHeader
        title={`Truth sheet: ${sku.name}`}
        description={
          <>
            The approved claims every page and AI answer is checked against. Saving re-checks the product straight away and
            keeps earlier versions as history.{" "}
            <CarryLink href={`/products/${sku.id}`} className="underline underline-offset-4">
              Back to product
            </CarryLink>
          </>
        }
      />
      <TruthSheetForm sku={sku} claims={claims} inferred={inferred} />
    </>
  );
}
