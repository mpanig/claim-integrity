import type { Metadata } from "next";
import { Suspense } from "react";
import { CrawlerActivity, type CrawlerData } from "@/components/aeo/crawler-activity";
import { type ReferralData, ReferralTraffic } from "@/components/aeo/referral-traffic";
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
        description="Which AI bots read your site, whether they may, and how many visitors AI assistants send you. From your own logs, analytics and robots.txt; we never pretend to be an AI bot."
        actions={<RunButton path="/audit/run" label="Check pages now" ok="Pages checked" />}
      />
      <Suspense fallback={<LoadingBlock rows={4} />}>
        <Crawlers />
      </Suspense>
    </>
  );
}

async function Crawlers() {
  const [crawl, refs, audits, brands, skus] = await Promise.all([
    serverGet<CrawlerData>("/aeo/crawlers"),
    serverGet<ReferralData>("/aeo/referrals"),
    serverGet<Audit[]>("/audit"),
    serverGet<Brand[]>("/brands"),
    serverGet<Sku[]>("/skus"),
  ]);
  return (
    <div className="flex flex-col gap-6">
      <CrawlerActivity data={crawl} />
      <ReferralTraffic data={refs} />
      <Card id="crawlability">
        <CardHeader>
          <CardTitle>Crawlability</CardTitle>
          <CardDescription>Which AI crawlers each page allows. Blocking search crawlers keeps you out of AI answers that cite sources.</CardDescription>
        </CardHeader>
        <CardContent>
          <PageAuditList audits={audits} brands={brands} skus={skus} show={["crawl"]} />
        </CardContent>
      </Card>
    </div>
  );
}
