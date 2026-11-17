import { ArrowRight, CircleCheck, Lightbulb } from "lucide-react";
import type { Metadata } from "next";
import { Suspense } from "react";
import { BarListChart } from "@/components/charts/bar-list-chart";
import { OpenVsFixedChart, ScoreTrendChart } from "@/components/charts/trend-charts";
import { brandColorMap } from "@/lib/chart-colors";
import { CarryLink, ConflictLink, DemoBadge, EmptyState, LoadingBlock, TimeAgo } from "@/components/common";
import { PageHeader } from "@/components/page-header";
import { DriftBadge, DriftHero, SeverityBadge, VerdictBadge } from "@/components/status";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { serverGet } from "@/lib/api";
import { describeEvent, FIELD_LABEL, snippet, VERDICT_LABEL, VERDICT_ORDER } from "@/lib/labels";
import { brandParam, rangeWeeks, type SP } from "@/lib/params";
import type { Recommendations } from "@/lib/recommendations";
import type { Brand, Summary, Trends } from "@/lib/types";

export const metadata: Metadata = { title: "Overview" };

export default function OverviewPage({ searchParams }: PageProps<"/">) {
  return (
    <>
      <PageHeader
        title="Overview"
        description="How consistently your products are described across retailers, professional sites and the brand site."
      />
      <Suspense fallback={<LoadingBlock rows={4} />}>
        <Overview searchParams={searchParams} />
      </Suspense>
    </>
  );
}

async function Overview({ searchParams }: { searchParams: Promise<SP> }) {
  const sp = await searchParams;
  const brand_id = brandParam(sp);
  const weeks = rangeWeeks(sp);
  const [s, t, allBrands, recs] = await Promise.all([
    serverGet<Summary>("/summary", { brand_id }),
    serverGet<Trends>("/trends", { brand_id, weeks }),
    serverGet<Brand[]>("/brands"),
    serverGet<Recommendations>("/recommendations", { brand_id }),
  ]);
  const nextActions = recs.items.filter((r) => r.state === "todo").slice(0, 3);
  const o = s.overall;
  const brandColors = brandColorMap(allBrands);

  if (o.skus === 0) {
    return (
      <EmptyState
        title="No products yet"
        action={
          <CarryLink href="/products/new" className="text-sm font-medium underline underline-offset-4">
            Add your first product
          </CarryLink>
        }
      >
        Add a product with its approved claims, then the pages that sell it, to start tracking consistency.
      </EmptyState>
    );
  }

  const highRisk = o.by_verdict.contradiction + o.by_verdict.risky;
  const inProgress = o.by_status.accepted + o.by_status.fixed;
  const byType = VERDICT_ORDER.map((v) => ({ label: VERDICT_LABEL[v], value: o.by_verdict[v] })).filter((d) => d.value > 0);

  return (
    <div className="flex flex-col gap-6">
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Card>
          <CardHeader>
            <CardDescription>Drift score</CardDescription>
          </CardHeader>
          <CardContent>
            <DriftHero drift={o.drift_score} label="All selected products" />
          </CardContent>
        </Card>
        <Kpi label="Open issues" value={o.unresolved} sub={`${highRisk} high risk (unapproved or contradictory claims)`} />
        <Kpi label="Being fixed" value={inProgress} sub={`${o.by_status.accepted} accepted · ${o.by_status.fixed} awaiting check`} />
        <Kpi label="Coverage" value={o.skus} sub={`products monitored on ${o.pages} pages`} />
      </div>

      {nextActions.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Lightbulb className="size-4 text-muted-foreground" /> Next best actions
            </CardTitle>
            <CardDescription>The highest-impact things to do this week.</CardDescription>
          </CardHeader>
          <CardContent>
            <ol className="grid gap-3 md:grid-cols-3">
              {nextActions.map((r, i) => (
                <li key={r.key} className="flex flex-col gap-1 rounded-lg border p-3">
                  <span className="text-xs text-muted-foreground">
                    {i + 1}. {r.owner_label}
                    {r.impact_points > 0 && ` · +${r.impact_points} pts`}
                  </span>
                  <span className="text-sm font-medium">{r.title}</span>
                  {r.is_demo && <DemoBadge className="mt-1 w-fit" />}
                </li>
              ))}
            </ol>
            <CarryLink href="/recommendations" className="mt-3 inline-flex items-center gap-1 text-sm underline-offset-4 hover:underline">
              See all {recs.items.length} recommendations <ArrowRight className="size-3.5" />
            </CarryLink>
          </CardContent>
        </Card>
      )}

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="flex flex-wrap items-center gap-2">Drift over time {t.demo && <DemoBadge />}</CardTitle>
            <CardDescription>
              Weekly drift score{t.brands.length > 1 ? " by brand" : ""}, last {weeks} weeks. Lower is better: 0 means every page matches the truth.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <ScoreTrendChart trends={t} brandColors={brandColors} />
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="flex flex-wrap items-center gap-2">Open issues vs fixes {t.demo && <DemoBadge />}</CardTitle>
            <CardDescription>Are issues being fixed faster than new ones appear?</CardDescription>
          </CardHeader>
          <CardContent>
            <OpenVsFixedChart trends={t} />
          </CardContent>
        </Card>
      </div>
      {!t.demo && t.weeks.filter((w) => w.score !== null).length < 2 && (
        <p className="-mt-2 text-xs text-muted-foreground">
          Trends fill in as checks run each week. For a preview, seed with <code>--demo-history</code> (shown with a
          “Demo data” badge).
        </p>
      )}

      {s.brands.length > 1 && (
        <section className="flex flex-col gap-3">
          <h2 className="text-sm font-medium">By brand</h2>
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            {s.brands.map((b) => (
              <CarryLink key={b.id} href={`/products?brand=${b.id}`} className="group">
                <Card className="transition-colors group-hover:bg-muted/40">
                  <CardHeader>
                    <CardTitle className="flex items-center justify-between gap-2">
                      {b.name}
                      <ArrowRight className="size-4 text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100" />
                    </CardTitle>
                    <CardDescription>
                      {b.skus} product{b.skus === 1 ? "" : "s"} · {b.unresolved} open issue{b.unresolved === 1 ? "" : "s"}
                    </CardDescription>
                  </CardHeader>
                  <CardContent>
                    <DriftBadge drift={b.drift_score} />
                  </CardContent>
                </Card>
              </CarryLink>
            ))}
          </div>
        </section>
      )}

      <div className="grid gap-4 lg:grid-cols-5">
        <Card className="lg:col-span-3">
          <CardHeader>
            <CardTitle>Top 5 to fix</CardTitle>
            <CardDescription>Highest risk first, weighted by how much each page matters.</CardDescription>
          </CardHeader>
          <CardContent>
            {s.top.length === 0 ? (
              <EmptyState title="Nothing to fix right now" icon={CircleCheck}>
                Every open issue has been accepted, fixed or dismissed.
              </EmptyState>
            ) : (
              <ul className="flex flex-col divide-y">
                {s.top.map((c) => (
                  <li key={c.id}>
                    <ConflictLink
                      id={c.id}
                      className="flex w-full flex-col gap-1.5 rounded-md px-1 py-3 hover:bg-muted/40 sm:flex-row sm:items-center sm:gap-3"
                    >
                      <VerdictBadge verdict={c.verdict} />
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-sm font-medium">
                          {FIELD_LABEL[c.field]} on {c.page_label}
                        </span>
                        <span className="block truncate text-xs text-muted-foreground">
                          {snippet(c)} · {c.sku_name}
                        </span>
                      </span>
                      <SeverityBadge severity={c.severity} />
                    </ConflictLink>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>

        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Open issues by type</CardTitle>
            <CardDescription>What kind of inconsistency is most common.</CardDescription>
          </CardHeader>
          <CardContent>
            {byType.length ? (
              <BarListChart data={byType} valueName="Open issues" labelWidth={160} />
            ) : (
              <EmptyState title="No open issues" icon={CircleCheck} />
            )}
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-4 lg:grid-cols-5">
        <Card className="lg:col-span-3">
          <CardHeader>
            <CardTitle>Open issues by source</CardTitle>
            <CardDescription>Which retailers and sites need the most attention.</CardDescription>
          </CardHeader>
          <CardContent>
            {s.by_source.length ? (
              <BarListChart
                data={s.by_source.map((x) => ({ label: x.label, value: x.unresolved }))}
                valueName="Open issues"
                labelWidth={120}
              />
            ) : (
              <EmptyState title="No open issues on any page" icon={CircleCheck} />
            )}
          </CardContent>
        </Card>
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardDescription>Mean time to fix</CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-1">
            {o.mean_days_to_fix === null ? (
              <>
                <span className="text-4xl font-semibold tracking-tight">–</span>
                <span className="text-xs text-muted-foreground">
                  No fixes verified yet. This shows the average days from an issue being found to its fix being verified.
                </span>
              </>
            ) : (
              <>
                <span className="text-4xl font-semibold tracking-tight">
                  {o.mean_days_to_fix} <span className="text-base font-normal text-muted-foreground">days</span>
                </span>
                <span className="text-xs text-muted-foreground">From an issue being found to its fix being verified.</span>
              </>
            )}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Recent activity</CardTitle>
        </CardHeader>
        <CardContent>
          {s.activity.length === 0 ? (
            <p className="text-sm text-muted-foreground">No activity yet.</p>
          ) : (
            <ul className="flex flex-col divide-y">
              {s.activity.map((e) => (
                <li key={e.id} className="flex flex-wrap items-baseline gap-x-2 py-2 text-sm">
                  <span className="font-medium">{e.actor === "system" ? "Automatic check" : e.actor}</span>
                  {e.conflict_id ? (
                    <ConflictLink id={e.conflict_id} className="text-muted-foreground hover:text-foreground">
                      {describeEvent(e.action, e.detail)}
                    </ConflictLink>
                  ) : (
                    <span className="text-muted-foreground">{describeEvent(e.action, e.detail)}</span>
                  )}
                  <span className="text-muted-foreground">· {e.sku_name}</span>
                  <TimeAgo iso={e.at} className="ml-auto text-xs text-muted-foreground" />
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function Kpi({ label, value, sub }: { label: string; value: number | string; sub: string }) {
  return (
    <Card>
      <CardHeader>
        <CardDescription>{label}</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-1">
        <span className="text-4xl font-semibold tracking-tight">{value}</span>
        <span className="text-xs text-muted-foreground">{sub}</span>
      </CardContent>
    </Card>
  );
}
