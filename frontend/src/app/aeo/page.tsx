import { Info, Repeat } from "lucide-react";
import type { Metadata } from "next";
import { Suspense } from "react";
import { AiFilters } from "@/components/ai/ai-filters";
import { MentionTrend, RankChart } from "@/components/ai/ai-charts";
import { AeoScoreSection } from "@/components/aeo/aeo-score";
import { AwaitingEngines } from "@/components/ai/awaiting-engines";
import { EngineStrip } from "@/components/ai/engine-strip";
import { HeatmapControls } from "@/components/ai/heatmap-controls";
import { ConflictLink, DemoBadge, EmptyState, LoadingBlock } from "@/components/common";
import { PageHeader } from "@/components/page-header";
import { Pill, VerdictBadge } from "@/components/status";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { type AeoScore, aiFilterParams, COUNTRY_LABEL, type EngineStatus, type Insights, type Library, pct, rateRange } from "@/lib/ai";
import { serverGet } from "@/lib/api";
import { SERIES } from "@/lib/chart-colors";
import { displayValue } from "@/lib/format";
import { first, type SP } from "@/lib/params";
import type { Verdict } from "@/lib/types";

export const metadata: Metadata = { title: "AEO / GEO overview" };

export default function AeoOverviewPage({ searchParams }: PageProps<"/aeo">) {
  return (
    <>
      <PageHeader
        title="AEO / GEO"
        description="Answer and generative engine optimisation: how AI assistants answer shopper questions about your category and products, who they mention and recommend, in what order, and whether the facts they state are right."
      />
      <Suspense fallback={<LoadingBlock rows={4} />}>
        <Overview searchParams={searchParams} />
      </Suspense>
    </>
  );
}

async function Overview({ searchParams }: { searchParams: Promise<SP> }) {
  const sp = await searchParams;
  const [ins, engines, lib, score] = await Promise.all([
    serverGet<Insights>("/ai/insights", aiFilterParams(sp)),
    serverGet<EngineStatus[]>("/ai/engines"),
    serverGet<Library>("/ai/library"),
    serverGet<AeoScore>("/ai/score", aiFilterParams(sp)),
  ]);
  const regions = [...new Set(ins.heatmap.map((h) => h.region))].sort();
  const own = ins.brands.filter((b) => b.is_own);
  const hmBrand = first(sp.hm_brand) ?? own[0]?.name ?? ins.brands[0]?.name ?? "";
  const hmMetric = first(sp.hm_metric) === "recommended" ? "recommended" : "mention";
  const colors = Object.fromEntries(own.map((b, i) => [b.name, SERIES[Math.min(i, SERIES.length - 1)]]));
  const keyed = ins.engines.some((e) => e.mode === "live" || e.mode === "awaiting");

  return (
    <div className="flex flex-col gap-6">
      <Alert>
        <Info />
        <AlertTitle>{keyed ? "Real answers for engines with keys, demo for the rest" : "Demo answers: no AI engine is connected yet"}</AlertTitle>
        <AlertDescription>
          Answers come from each provider&apos;s official API, which has no account memory or personalisation like the
          consumer apps. We set the context instead: persona, region and language. Region goes through the API where it
          supports a user location, otherwise into the question. Engines without an API key show demo answers, marked
          Demo data, until a key is added.
        </AlertDescription>
      </Alert>

      <div className="flex flex-col gap-3">
        <EngineStrip modes={ins.engines} statuses={engines} />
        <AwaitingEngines modes={ins.engines} />
        <AiFilters personas={lib.personas} regions={regions.length ? regions : ["US", "IN"]} />
      </div>

      {ins.answers === 0 ? (
        <EmptyState title="No answers for these filters">Run a test plan, or clear the filters.</EmptyState>
      ) : (
        <>
          <AeoScoreSection score={score} />
          <Card>
            <CardHeader>
              <CardTitle className="flex flex-wrap items-center gap-2">
                Brands in AI answers {ins.demo && <DemoBadge />}
              </CardTitle>
              <CardDescription>
                {ins.answers} answers. Rates show the 95% range in brackets: with few answers the true rate could be anywhere in it.
              </CardDescription>
            </CardHeader>
            <CardContent className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Brand</TableHead>
                    <TableHead>Mentioned in</TableHead>
                    <TableHead>Recommended in</TableHead>
                    <TableHead>In top 3</TableHead>
                    <TableHead className="text-right">Share of voice</TableHead>
                    <TableHead className="text-right">Avg. rank</TableHead>
                    <TableHead className="text-right">Sentiment</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {ins.brands.map((b) => (
                    <TableRow key={b.name}>
                      <TableCell className="font-medium">
                        {b.name} {b.is_own ? <Pill tone="good">Ours</Pill> : <span className="text-xs text-muted-foreground">competitor</span>}
                      </TableCell>
                      <TableCell className="tabular-nums">{rateRange(b.mention)}</TableCell>
                      <TableCell className="tabular-nums">{rateRange(b.recommended)}</TableCell>
                      <TableCell className="tabular-nums">{rateRange(b.top3)}</TableCell>
                      <TableCell className="text-right tabular-nums">{pct(b.share_of_voice)}</TableCell>
                      <TableCell className="text-right tabular-nums">{b.avg_position ?? "–"}</TableCell>
                      <TableCell className="text-right tabular-nums">{b.sentiment === null ? "–" : b.sentiment > 0 ? `+${b.sentiment}` : b.sentiment}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="flex flex-wrap items-center gap-2">Where a brand shows up {ins.demo && <DemoBadge />}</CardTitle>
              <CardDescription>Share of answers by engine and region (rows) and persona (columns). Darker means more often.</CardDescription>
            </CardHeader>
            <CardContent className="flex flex-col gap-3">
              <HeatmapControls brands={ins.brands.map((b) => b.name)} brand={hmBrand} metric={hmMetric} />
              <Heatmap ins={ins} brand={hmBrand} metric={hmMetric} />
            </CardContent>
          </Card>

          <div className="grid gap-4 lg:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle className="flex flex-wrap items-center gap-2">Rank in list answers {ins.demo && <DemoBadge />}</CardTitle>
                <CardDescription>How often each brand is listed first, second, and so on.</CardDescription>
              </CardHeader>
              <CardContent>
                <RankChart rank={ins.rank} />
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle className="flex flex-wrap items-center gap-2">Our brands over time {ins.demo && <DemoBadge />}</CardTitle>
                <CardDescription>Share of answers that mention each of our brands, by week.</CardDescription>
              </CardHeader>
              <CardContent>
                {ins.trend.length > 1 ? (
                  <MentionTrend trend={ins.trend} brands={own.map((b) => b.name)} colors={colors} />
                ) : (
                  <p className="text-sm text-muted-foreground">Trends appear after answers from more than one week.</p>
                )}
              </CardContent>
            </Card>
          </div>

          <Card>
            <CardHeader>
              <CardTitle className="flex flex-wrap items-center gap-2">Are the facts right? {ins.demo && <DemoBadge />}</CardTitle>
              <CardDescription>
                Product facts stated in answers, checked against your truth sheets. “Repeats” links an AI mistake to an open
                issue on a retailer page, which is often where the AI picked it up.
              </CardDescription>
            </CardHeader>
            <CardContent className="flex flex-col gap-4">
              {ins.accuracy.length === 0 ? (
                <p className="text-sm text-muted-foreground">No product facts stated in these answers.</p>
              ) : (
                <div className="grid gap-3 md:grid-cols-2">
                  {ins.accuracy.map((a) => (
                    <div key={a.sku_id} className="flex flex-col gap-2 rounded-xl border p-3">
                      <p className="font-medium">{a.sku_name}</p>
                      <p className="text-sm text-muted-foreground">
                        {a.claims} facts stated · {rateRange(a.accuracy)} correct
                      </p>
                      <div className="flex flex-wrap gap-1.5">
                        {Object.entries(a.by_verdict).map(([v, n]) => (
                          <span key={v} className="flex items-center gap-1 text-xs">
                            <VerdictBadge verdict={v as Verdict} label={v === "outdated" ? "Outdated ingredient info" : undefined} /> × {n}
                          </span>
                        ))}
                      </div>
                      {a.echoes.map((e) => (
                        <ConflictLink key={e.conflict_id} id={e.conflict_id} className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground">
                          <Repeat className="size-3.5" /> Repeats {e.label} in {e.answers} answers
                        </ConflictLink>
                      ))}
                    </div>
                  ))}
                </div>
              )}
              {ins.wrong_claims.length > 0 && (
                <details className="rounded-xl border p-3">
                  <summary className="cursor-pointer text-sm font-medium">Examples of wrong or unapproved facts</summary>
                  <ul className="mt-2 flex flex-col divide-y">
                    {ins.wrong_claims.slice(0, 12).map((w, i) => (
                      <li key={i} className="flex flex-col gap-1 py-2 text-sm">
                        <span className="flex flex-wrap items-center gap-2">
                          <VerdictBadge verdict={w.verdict as Verdict} label={w.verdict === "outdated" ? "Outdated ingredient info" : undefined} />
                          <span className="font-medium">{displayValue(w.value)}</span>
                          <span className="text-xs text-muted-foreground">
                            {w.sku_name} · {w.engine} · {COUNTRY_LABEL[w.region] ?? w.region}
                          </span>
                        </span>
                        <span className="text-xs text-muted-foreground">“{w.quote}”</span>
                      </li>
                    ))}
                  </ul>
                </details>
              )}
            </CardContent>
          </Card>

        </>
      )}
    </div>
  );
}

function Heatmap({ ins, brand, metric }: { ins: Insights; brand: string; metric: "mention" | "recommended" }) {
  const cells = ins.heatmap.filter((h) => h.brand === brand);
  const personas = [...new Set(cells.map((c) => c.persona))].sort((a, b) => (a === "No persona" ? -1 : b === "No persona" ? 1 : a.localeCompare(b)));
  const rows = [...new Set(cells.map((c) => `${c.engine}|${c.region}`))].sort();
  const label = Object.fromEntries(ins.engines.map((e) => [e.engine, e.label]));
  if (!cells.length) return <p className="text-sm text-muted-foreground">No answers mention {brand}.</p>;
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[640px] border-separate border-spacing-1 text-sm">
        <thead>
          <tr>
            <th className="text-left text-xs font-medium text-muted-foreground">Engine · region</th>
            {personas.map((p) => (
              <th key={p} className="text-left text-xs font-medium text-muted-foreground">
                {p}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const [engine, region] = row.split("|");
            return (
              <tr key={row}>
                <th scope="row" className="pr-2 text-left font-medium whitespace-nowrap">
                  {label[engine] ?? engine} · {region}
                </th>
                {personas.map((p) => {
                  const c = cells.find((x) => x.engine === engine && x.region === region && x.persona === p);
                  const r = c ? c[metric] : null;
                  return (
                    <td
                      key={p}
                      className="h-12 min-w-24 rounded-md ring-1 ring-border ring-inset"
                      style={{ background: r?.rate != null ? `color-mix(in oklab, var(--series-1) ${Math.max(5, Math.round(r.rate * 100))}%, transparent)` : undefined }}
                      title={r ? `${r.k} of ${r.n} answers; 95% range ${pct(r.low)}–${pct(r.high)}` : undefined}
                    >
                      <div className="flex h-full flex-col items-start justify-center px-2">
                        <span className="rounded bg-background/85 px-1 font-medium tabular-nums">{r ? pct(r.rate) : "–"}</span>
                        {r && <span className="rounded bg-background/70 px-1 text-[11px] text-muted-foreground">n = {r.n}</span>}
                      </div>
                    </td>
                  );
                })}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
