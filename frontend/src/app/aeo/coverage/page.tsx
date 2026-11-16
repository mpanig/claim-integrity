import type { Metadata } from "next";
import { AwaitingEngines } from "@/components/ai/awaiting-engines";
import { Suspense } from "react";
import { AiFilters } from "@/components/ai/ai-filters";
import { DemoBadge, EmptyState, LoadingBlock } from "@/components/common";
import { PageHeader } from "@/components/page-header";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { aiFilterParams, type EngineMode, type Library, pct, type Rate, rateRange } from "@/lib/ai";
import { serverGet } from "@/lib/api";
import type { SP } from "@/lib/params";

export const metadata: Metadata = { title: "AEO coverage" };

interface Coverage {
  answers: number;
  demo: boolean;
  engines: EngineMode[];
  use_cases: { use_case: string; persona: string; answers: number; our_brand: string | null; ours: Rate; top_competitor: string | null; competitor: Rate; gap: number }[];
}

export default function CoveragePage({ searchParams }: PageProps<"/aeo/coverage">) {
  return (
    <>
      <PageHeader title="Coverage" description="Shopper situations where AI assistants recommend a competitor instead of you." />
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
    </div>
  );
}
