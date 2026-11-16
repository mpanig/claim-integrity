import { Info } from "lucide-react";
import type { Metadata } from "next";
import { Suspense } from "react";
import { RunButton } from "@/components/audit/audit-actions";
import { type Audit, type Entity, EntityClarity, PageAuditList } from "@/components/audit/page-audits";
import { LlmsList, type LlmsRow } from "@/components/aeo/llms";
import { BriefBuilder, GradeForm, GradeList } from "@/components/aeo/readiness";
import { DemoBadge, LoadingBlock } from "@/components/common";
import { PageHeader } from "@/components/page-header";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import type { AnswerGradeRow, Library } from "@/lib/ai";
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
  const [audits, entities, brands, skus, grades, lib, llms] = await Promise.all([
    serverGet<Audit[]>("/audit"),
    serverGet<Entity[]>("/audit/entities"),
    serverGet<Brand[]>("/brands"),
    serverGet<Sku[]>("/skus"),
    serverGet<AnswerGradeRow[]>("/aeo/grades"),
    serverGet<Library>("/ai/library"),
    serverGet<LlmsRow[]>("/aeo/llms"),
  ]);
  return (
    <div className="flex flex-col gap-6">
      <Card id="readiness">
        <CardHeader>
          <CardTitle className="flex flex-wrap items-center gap-2">
            Answer-readiness {grades.some((g) => g.is_demo) && <DemoBadge />}
          </CardTitle>
          <CardDescription>
            How easy each page is for AI assistants to quote correctly, out of 100, with what to fix. Each grade fetches the
            page once, after checking robots.txt. Demo grades use bundled sample pages and disappear once you grade that URL.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <GradeForm />
          {grades.length ? <GradeList grades={grades} /> : <p className="text-sm text-muted-foreground">No pages graded yet.</p>}
        </CardContent>
      </Card>
      <Card id="brief">
        <CardHeader>
          <CardTitle>Content brief</CardTitle>
          <CardDescription>
            What a page should say to win one AI question: built from your truth sheet, positioning, what AI gets wrong,
            competitors and gap sites. Copy or download it as Markdown for your writers.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <BriefBuilder
            brands={brands.map((b) => ({ id: b.id, name: b.name }))}
            skus={skus.map((s) => ({ id: s.id, name: s.name, brand_id: s.brand_id }))}
            suggestions={lib.prompts
              .map((p) => p.text.replaceAll("{category}", p.category ?? "face cleanser").replaceAll("{competitor}", p.competitor ?? "").replaceAll("{product}", p.sku_name ?? ""))
              .filter((t) => !/[{}]/.test(t))}
          />
        </CardContent>
      </Card>
      <Card id="llms">
        <CardHeader>
          <CardTitle className="flex flex-wrap items-center gap-2">llms.txt {llms.some((r) => r.is_demo) && <DemoBadge />}</CardTitle>
          <CardDescription>
            A short Markdown file at your site&apos;s root that points AI tools to your key pages (llmstxt.org format). Checked
            once per brand site after robots.txt; draft one from your product data if it&apos;s missing.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <div>
            <RunButton path="/aeo/llms/check" label="Check llms.txt now" ok="llms.txt checked" />
          </div>
          <LlmsList rows={llms} />
        </CardContent>
      </Card>
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
