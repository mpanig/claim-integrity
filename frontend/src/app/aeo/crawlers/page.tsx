import type { Metadata } from "next";
import { Suspense } from "react";
import { RunButton } from "@/components/audit/audit-actions";
import { type Audit, PageAuditList } from "@/components/audit/page-audits";
import { LoadingBlock } from "@/components/common";
import { PageHeader } from "@/components/page-header";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { serverGet } from "@/lib/api";
import type { Brand, Sku } from "@/lib/types";

export const metadata: Metadata = { title: "AEO crawlers & traffic" };

export default function CrawlersPage() {
  return (
    <>
      <PageHeader
        title="Crawlers & traffic"
        description="Whether AI crawlers may read your pages. Read from robots.txt rules and page tags; we never pretend to be an AI bot."
        actions={<RunButton path="/audit/run" label="Check pages now" ok="Pages checked" />}
      />
      <Suspense fallback={<LoadingBlock rows={3} />}>
        <Crawlability />
      </Suspense>
    </>
  );
}

async function Crawlability() {
  const [audits, brands, skus] = await Promise.all([serverGet<Audit[]>("/audit"), serverGet<Brand[]>("/brands"), serverGet<Sku[]>("/skus")]);
  return (
    <Card id="crawlability">
      <CardHeader>
        <CardTitle>Crawlability</CardTitle>
        <CardDescription>Which AI crawlers each page allows. Blocking search crawlers keeps you out of AI answers that cite sources.</CardDescription>
      </CardHeader>
      <CardContent>
        <PageAuditList audits={audits} brands={brands} skus={skus} show={["crawl"]} />
      </CardContent>
    </Card>
  );
}
