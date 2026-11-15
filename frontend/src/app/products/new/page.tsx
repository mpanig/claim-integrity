import type { Metadata } from "next";
import { Suspense } from "react";
import { LoadingBlock } from "@/components/common";
import { PageHeader } from "@/components/page-header";
import { TruthSheetForm } from "@/components/truth-sheet-form";
import { serverGet } from "@/lib/api";
import type { Brand } from "@/lib/types";

export const metadata: Metadata = { title: "Add product" };

export default function NewProductPage() {
  return (
    <>
      <PageHeader
        title="Add a product"
        description="Enter the approved claims for the product. Pages that sell it are compared against this truth sheet."
      />
      <Suspense fallback={<LoadingBlock rows={2} />}>
        <NewProductForm />
      </Suspense>
    </>
  );
}

async function NewProductForm() {
  const brands = await serverGet<Brand[]>("/brands");
  return <TruthSheetForm brands={brands} />;
}
