import type { Metadata } from "next";
import { AwaitingEngines } from "@/components/ai/awaiting-engines";
import { Suspense } from "react";
import { AiFilters } from "@/components/ai/ai-filters";
import { AiTabs } from "@/components/ai/ai-tabs";
import { DemoBadge, EmptyState, LoadingBlock } from "@/components/common";
import { PageHeader } from "@/components/page-header";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { aiFilterParams, type EngineMode, type Library, pct, type Rate, rateRange } from "@/lib/ai";
import { serverGet } from "@/lib/api";
import type { SP } from "@/lib/params";

export const metadata: Metadata = { title: "AI coverage" };

interface Coverage {
  answers: number;
  demo: boolean;
  engines: EngineMode[];
  third_party: { domain: string; page_type: string; citations: number; with_our_brand: number; gap: number }[];
  use_cases: { use_case: string; persona: string; answers: number; our_brand: string | null; ours: Rate; top_competitor: string | null; competitor: Rate; gap: number }[];
}

export default function CoveragePage({ searchParams }: PageProps<"/ai-visibility/coverage">) {
  return (
    <>
      <PageHeader title="AI visibility" description="Which situations AI assistants recommend competitors in instead of you, and which outside sites shape those answers." />
      <AiTabs />
      <Suspense fallback={<LoadingBlock rows={3} />}>
        <CoverageView searchParams={searchParams} />
      </Suspense>
    </>
  );
}

async function CoverageView({ searchParams }: { searchParams: Promise<SP> }) {
  const sp = await searchParams;
  const [cov, lib] = await Promise.all([serverGet<Coverage>("/ai/coverage", aiFilterParams(sp)), serverGet<Library>("/ai/library")]);
  if (cov.answers === 0)
    return (
      <div className="flex flex-col gap-6">
        <AwaitingEngines modes={cov.engines} />
        <EmptyState title="No answers for these filters">Run a test plan, or clear the filters.</EmptyState>
      </div>
    );
  return (
    <div className="flex flex-col gap-6">
      <AiFilters personas={lib.personas} regions={["US", "IN", "GB"]} />
      <AwaitingEngines modes={cov.engines} />
      <Card>
        <CardHeader>
          <CardTitle className="flex flex-wrap items-center gap-2">Use-case coverage {cov.demo && <DemoBadge />}</CardTitle>
          <CardDescription>For each kind of question and shopper, how often our best brand is mentioned versus the leading competitor. Biggest gaps first.</CardDescription>
        </CardHeader>
        <CardContent className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Use case</TableHead>
                <TableHead>Shopper</TableHead>
                <TableHead>Us</TableHead>
                <TableHead>Leading competitor</TableHead>
                <TableHead className="text-right">Gap</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {cov.use_cases.map((u) => (
                <TableRow key={`${u.use_case}|${u.persona}`}>
                  <TableCell className="max-w-72 font-medium">{u.use_case}</TableCell>
                  <TableCell className="text-muted-foreground">{u.persona}</TableCell>
                  <TableCell className="tabular-nums">
                    {u.our_brand ?? "not mentioned"} · {rateRange(u.ours)}
                  </TableCell>
                  <TableCell className="tabular-nums">{u.top_competitor ? `${u.top_competitor} · ${rateRange(u.competitor)}` : "–"}</TableCell>
                  <TableCell className="text-right tabular-nums">{u.gap > 0 ? `+${pct(u.gap)} to them` : u.gap < 0 ? `${pct(-u.gap)} ahead` : "even"}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle className="flex flex-wrap items-center gap-2">Third-party sites in AI answers {cov.demo && <DemoBadge />}</CardTitle>
          <CardDescription>
            Outside sites the answers cite. “Gap” counts citations in answers that recommend a competitor and don&apos;t mention us; those sites are worth outreach.
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
    </div>
  );
}
