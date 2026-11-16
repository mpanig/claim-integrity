import { Info } from "lucide-react";
import type { Metadata } from "next";
import { Suspense } from "react";
import { RunButton } from "@/components/audit/audit-actions";
import { type Audit, type Entity, EntityClarity, PageAuditList } from "@/components/audit/page-audits";
import { LoadingBlock } from "@/components/common";
import { PageHeader } from "@/components/page-header";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { serverGet } from "@/lib/api";
import type { Brand, Sku } from "@/lib/types";

export const metadata: Metadata = { title: "AEO content & pages" };

export default function ContentPage() {
  return (
    <>
      <PageHeader
        title="Content & pages"
        description="Can AI tools read clear, current facts about your products and brand? Pages you add here are checked; nothing else is crawled."
        actions={
          <>
            <RunButton path="/audit/run" label="Check pages now" ok="Pages checked" />
            <RunButton path="/audit/entities/run" label="Check brand entities" ok="Wikidata checked" />
          </>
        }
      />
      <Alert>
        <Info />
        <AlertTitle>How pages are checked</AlertTitle>
        <AlertDescription>
          Each page is fetched once with an honest user agent, after checking the site&apos;s robots.txt. Pages re-check
          weekly when the background worker runs. AI crawler access for the same pages is under Crawlers &amp; traffic.
        </AlertDescription>
      </Alert>
      <Suspense fallback={<LoadingBlock rows={3} />}>
        <Content />
      </Suspense>
    </>
  );
}

async function Content() {
  const [audits, entities, brands, skus] = await Promise.all([
    serverGet<Audit[]>("/audit"),
    serverGet<Entity[]>("/audit/entities"),
    serverGet<Brand[]>("/brands"),
    serverGet<Sku[]>("/skus"),
  ]);
  return (
    <div className="flex flex-col gap-6">
      <Card>
        <CardHeader>
          <CardTitle>Structured data and freshness</CardTitle>
          <CardDescription>Product data (schema.org) AI tools can read, and how current each page is.</CardDescription>
        </CardHeader>
        <CardContent>
          <PageAuditList audits={audits} brands={brands} skus={skus} show={["structured", "freshness"]} />
        </CardContent>
      </Card>
      <Card id="entity">
        <CardHeader>
          <CardTitle>Brand entity clarity</CardTitle>
          <CardDescription>AI models lean on Wikidata and Wikipedia for brand facts. Missing facts make answers vaguer or wrong.</CardDescription>
        </CardHeader>
        <CardContent>
          <EntityClarity entities={entities} />
        </CardContent>
      </Card>
    </div>
  );
}
