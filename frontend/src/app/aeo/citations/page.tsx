import type { Metadata } from "next";
import { Suspense } from "react";
import { AiFilters } from "@/components/ai/ai-filters";
import { BarListChart } from "@/components/charts/bar-list-chart";
import { DemoBadge, EmptyState, LoadingBlock } from "@/components/common";
import { PageHeader } from "@/components/page-header";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { aiFilterParams, type Insights, type Library } from "@/lib/ai";
import { serverGet } from "@/lib/api";
import type { SP } from "@/lib/params";

export const metadata: Metadata = { title: "AEO citations & sources" };

interface ThirdParty {
  answers: number;
  demo: boolean;
  third_party: { domain: string; page_type: string; citations: number; with_our_brand: number; gap: number }[];
}

export default function CitationsPage({ searchParams }: PageProps<"/aeo/citations">) {
  return (
    <>
      <PageHeader title="Citations & sources" description="The sites AI answers cite, and the ones that send shoppers to competitors instead of you." />
      <Suspense fallback={<LoadingBlock rows={3} />}>
        <Citations searchParams={searchParams} />
      </Suspense>
    </>
  );
}

async function Citations({ searchParams }: { searchParams: Promise<SP> }) {
  const sp = await searchParams;
  const params = aiFilterParams(sp);
  const [ins, cov, lib] = await Promise.all([
    serverGet<Insights>("/ai/insights", params),
    serverGet<ThirdParty>("/ai/coverage", params),
    serverGet<Library>("/ai/library"),
  ]);
  const regions = [...new Set(ins.heatmap.map((h) => h.region))].sort();
  return (
    <div className="flex flex-col gap-6">
      <AiFilters personas={lib.personas} regions={regions.length ? regions : ["US", "IN"]} />
      {ins.citations.total === 0 ? (
        <EmptyState title="No citations for these filters">Engines only cite sources with web search on.</EmptyState>
      ) : (
        <>
          <div className="grid gap-4 lg:grid-cols-5">
            <Card className="lg:col-span-3">
              <CardHeader>
                <CardTitle className="flex flex-wrap items-center gap-2">Most cited sites {ins.demo && <DemoBadge />}</CardTitle>
                <CardDescription>{ins.citations.total} citations. Getting these sites right improves what the AI says.</CardDescription>
              </CardHeader>
              <CardContent>
                <BarListChart data={ins.citations.domains.map((d) => ({ label: d.domain, value: d.count }))} valueName="Citations" labelWidth={160} />
              </CardContent>
            </Card>
            <Card className="lg:col-span-2">
              <CardHeader>
                <CardTitle className="flex flex-wrap items-center gap-2">By type of source {ins.demo && <DemoBadge />}</CardTitle>
              </CardHeader>
              <CardContent>
                <BarListChart
                  data={Object.entries(ins.citations.by_type)
                    .sort((a, b) => b[1] - a[1])
                    .map(([k, v]) => ({ label: k, value: v }))}
                  valueName="Citations"
                  labelWidth={90}
                />
              </CardContent>
            </Card>
          </div>
          <Card id="gaps">
            <CardHeader>
              <CardTitle className="flex flex-wrap items-center gap-2">Third-party sites and gaps {cov.demo && <DemoBadge />}</CardTitle>
              <CardDescription>
                Outside sites the answers cite. “Gap” counts citations in answers that recommend a competitor and don&apos;t mention
                us; those sites are worth outreach.
              </CardDescription>
            </CardHeader>
            <CardContent className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Site</TableHead>
                    <TableHead>Type</TableHead>
                    <TableHead className="text-right">Citations</TableHead>
                    <TableHead className="text-right">With our brand</TableHead>
                    <TableHead className="text-right">Gap</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {cov.third_party.map((d) => (
                    <TableRow key={d.domain}>
                      <TableCell className="font-medium">{d.domain}</TableCell>
                      <TableCell className="text-muted-foreground">{d.page_type}</TableCell>
                      <TableCell className="text-right tabular-nums">{d.citations}</TableCell>
                      <TableCell className="text-right tabular-nums">{d.with_our_brand}</TableCell>
                      <TableCell className="text-right tabular-nums">{d.gap}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}
