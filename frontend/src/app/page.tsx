import { ArrowRight, CircleCheck } from "lucide-react";
import type { Metadata } from "next";
import { Suspense } from "react";
import { BarListChart } from "@/components/charts/bar-list-chart";
import { CarryLink, ConflictLink, EmptyState, LoadingBlock, TimeAgo } from "@/components/common";
import { PageHeader } from "@/components/page-header";
import { ScoreBadge, ScoreHero, SeverityBadge, VerdictBadge } from "@/components/status";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { serverGet } from "@/lib/api";
import { describeEvent, FIELD_LABEL, snippet, VERDICT_LABEL, VERDICT_ORDER } from "@/lib/labels";
import { brandParam, type SP } from "@/lib/params";
import type { Summary } from "@/lib/types";

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
  const s = await serverGet<Summary>("/summary", { brand_id: brandParam(sp) });
  const o = s.overall;

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
            <CardDescription>Consistency score</CardDescription>
          </CardHeader>
          <CardContent>
            <ScoreHero score={o.score} label="All selected products" />
          </CardContent>
        </Card>
        <Kpi label="Open issues" value={o.unresolved} sub={`${highRisk} high risk (unapproved or contradictory claims)`} />
        <Kpi label="Being fixed" value={inProgress} sub={`${o.by_status.accepted} accepted · ${o.by_status.fixed} awaiting check`} />
        <Kpi label="Coverage" value={o.skus} sub={`products monitored on ${o.pages} pages`} />
      </div>

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
                    <ScoreBadge score={b.score} />
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
                          {c.sku_name} · {c.brand_name}
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
