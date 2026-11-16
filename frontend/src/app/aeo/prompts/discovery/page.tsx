import { Info } from "lucide-react";
import type { Metadata } from "next";
import { Suspense } from "react";
import { DiscoveryList } from "@/components/aeo/discovery-list";
import { PromptTabs } from "@/components/aeo/prompt-tabs";
import { LoadingBlock } from "@/components/common";
import { PageHeader } from "@/components/page-header";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import type { Discovery } from "@/lib/ai";
import { serverGet } from "@/lib/api";
import { first, type SP } from "@/lib/params";

export const metadata: Metadata = { title: "AEO prompt discovery" };

export default function DiscoveryPage({ searchParams }: PageProps<"/aeo/prompts/discovery">) {
  return (
    <>
      <PageHeader title="Prompts" description="Questions shoppers likely ask AI that you don't test yet, ranked by an estimate of how much they matter to you." />
      <PromptTabs />
      <Suspense fallback={<LoadingBlock rows={4} />}>
        <DiscoveryView searchParams={searchParams} />
      </Suspense>
    </>
  );
}

async function DiscoveryView({ searchParams }: { searchParams: Promise<SP> }) {
  const sp = await searchParams;
  const data = await serverGet<Discovery>("/ai/discovery", { llm: first(sp.llm) === "1" ? "true" : undefined });
  return (
    <div className="flex flex-col gap-6">
      <Alert>
        <Info />
        <AlertTitle>Importance is an estimate</AlertTitle>
        <AlertDescription>
          {data.importance_note} It rises when a question touches an attribute your positioning wants but AI rarely gives
          you, an attribute a competitor owns, or a question type competitors win. Each score lists its reasons.
        </AlertDescription>
      </Alert>
      <Card>
        <CardHeader>
          <CardTitle>Suggested prompts</CardTitle>
          <CardDescription>
            {data.candidates.length} new questions from your categories, products, competitors, personas and positioning;{" "}
            {data.already_covered} more {data.already_covered === 1 ? "is" : "are"} already in the library.{" "}
            {data.llm === "no key" ? "Add an Anthropic key to also get suggestions from Claude." : null}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <DiscoveryList data={data} />
        </CardContent>
      </Card>
    </div>
  );
}
