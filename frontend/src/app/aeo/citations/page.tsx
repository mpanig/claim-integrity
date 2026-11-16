import type { Metadata } from "next";
import { Suspense } from "react";
import { AddOutreach, OutreachBoard, type OutreachData } from "@/components/aeo/outreach";
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
  const [ins, cov, lib, outreach] = await Promise.all([
    serverGet<Insights>("/ai/insights", params),
    serverGet<ThirdParty>("/ai/coverage", params),
    serverGet<Library>("/ai/library"),
    serverGet<OutreachData>("/aeo/outreach"),
  ]);
  const tracked = new Set(outreach.rows.map((r) => r.domain));
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
                    <TableHead className="w-24" />
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
                      <TableCell className="text-right">
                        {tracked.has(d.domain) ? (
                          <span className="text-xs text-muted-foreground">Tracked</span>
                        ) : outreach.suggestions.some((s) => s.domain === d.domain) ? (
                          <AddOutreach domain={d.domain} />
                        ) : null}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </>
      )}
      <Card id="outreach">
        <CardHeader>
          <CardTitle className="flex flex-wrap items-center gap-2">Citation outreach {outreach.demo && <DemoBadge />}</CardTitle>
          <CardDescription>
            Work the sites AI answers cite so they mention your brands accurately. Start with gap sites: they are cited when a
            competitor is recommended and you aren&apos;t. Demo rows show until you track your first site.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          {outreach.suggestions.length > 0 && (
            <div className="flex flex-col gap-2">
              <h3 className="text-sm font-medium">Suggested: gap sites not tracked yet</h3>
              <ul className="flex flex-wrap gap-2">
                {outreach.suggestions.map((s) => (
                  <li key={s.domain} className="flex items-center gap-2 rounded-lg border px-2 py-1 text-sm">
                    <span className="font-medium">{s.domain}</span>
                    <span className="text-xs text-muted-foreground">
                      {s.gap} gap of {s.citations}
                    </span>
                    <AddOutreach domain={s.domain} />
                  </li>
                ))}
              </ul>
            </div>
          )}
          <AddOutreach />
          <OutreachBoard data={outreach} />
        </CardContent>
      </Card>
    </div>
  );
}
