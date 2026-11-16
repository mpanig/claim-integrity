import type { Metadata } from "next";
import { Suspense } from "react";
import { AiTabs } from "@/components/ai/ai-tabs";
import { LibraryEditor } from "@/components/ai/library-editor";
import { LoadingBlock } from "@/components/common";
import { PageHeader } from "@/components/page-header";
import type { Library } from "@/lib/ai";
import { serverGet } from "@/lib/api";

export const metadata: Metadata = { title: "AI prompt library" };

export default function LibraryPage() {
  return (
    <>
      <PageHeader title="AI visibility" description="The questions, wordings, personas and brand names the AI tests use." />
      <AiTabs />
      <Suspense fallback={<LoadingBlock rows={3} />}>
        <LibraryLoader />
      </Suspense>
    </>
  );
}

async function LibraryLoader() {
  return <LibraryEditor lib={await serverGet<Library>("/ai/library")} />;
}
