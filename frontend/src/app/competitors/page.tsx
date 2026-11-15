import { Lightbulb } from "lucide-react";
import type { Metadata } from "next";
import { Suspense } from "react";
import { BarListChart } from "@/components/charts/bar-list-chart";
import { CarryLink, EmptyState, LoadingBlock } from "@/components/common";
import { PageHeader } from "@/components/page-header";
import { ScoreBadge } from "@/components/status";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { serverGet } from "@/lib/api";
import { FIELD_LABEL } from "@/lib/labels";
import type { Field } from "@/lib/types";

export const metadata: Metadata = { title: "Competitors" };

type Category = "free_from" | "seals" | "clinical" | "claims";
interface BrandCompare {
  id: number;
  name: string;
  skus: number;
  pages: number;
  score: number | null;
  unresolved: number;
  issues_per_product: number;
  approved: Record<Category, string[]>;
  unapproved_on_pages: Record<Category, string[]>;
  heatmap: Record<Field, { checked: number; with_issues: number; consistent_pct: number | null }>;
}
interface Compare {
  categories: Record<Category, string>;
  fields: Field[];
  brands: BrandCompare[];
}

export default function CompetitorsPage() {
  return (
    <>
      <PageHeader
        title="Competitors"
        description="How the brands in your workspace compare: consistency, issues per product and which claims each one makes."
      />
      <Suspense fallback={<LoadingBlock rows={3} />}>
        <Competitors />
      </Suspense>
    </>
  );
}

function insights(brands: BrandCompare[]): string[] {
  const scored = brands.filter((b) => b.score !== null).sort((a, b) => (b.score ?? 0) - (a.score ?? 0));
  const out: string[] = [];
  if (scored.length >= 2) {
    const [best, worst] = [scored[0], scored[scored.length - 1]];
    out.push(
      `${best.name} is the most consistent (${best.score}/100). ${worst.name} trails at ${worst.score}/100 with ${worst.issues_per_product} open issues per product.`,
    );
  }
  for (const b of brands) {
    const clinical = b.unapproved_on_pages.clinical.length;
    const unapproved = Object.values(b.unapproved_on_pages).reduce((n, l) => n + l.length, 0);
    if (unapproved)
      out.push(
        `${b.name}'s pages show ${unapproved} claim${unapproved === 1 ? "" : "s"} the brand hasn't approved${
          clinical ? `, ${clinical} of them clinical or testing claims that need substantiation` : ""
        }.`,
      );
    if (!b.approved.free_from.length && b.unapproved_on_pages.free_from.length)
      out.push(
        `${b.name} approves no free-from claims, yet its pages advertise ${b.unapproved_on_pages.free_from.length}. Approve the true ones or ask for them to be removed.`,
      );
    if (!b.approved.seals.length && brands.some((o) => o.id !== b.id && o.approved.seals.length))
      out.push(`${b.name} has no seals or endorsements on record, while a competitor does.`);
  }
  return out;
}

async function Competitors() {
  const c = await serverGet<Compare>("/competitors");
  if (c.brands.length < 2) {
    return (
      <EmptyState
        title="Add a second brand to compare"
        action={
          <CarryLink href="/products/new" className="text-sm font-medium underline underline-offset-4">
            Add a product
          </CarryLink>
        }
      >
        Comparisons need at least two brands with products.
      </EmptyState>
    );
  }
  const notes = insights(c.brands);
  const cats = Object.keys(c.categories) as Category[];

  return (
    <div className="flex flex-col gap-6">
      {notes.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Lightbulb className="size-4 text-muted-foreground" /> What stands out
            </CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="flex list-disc flex-col gap-1.5 pl-5 text-sm">
              {notes.map((n) => (
                <li key={n}>{n}</li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {c.brands.map((b) => (
          <Card key={b.id}>
            <CardHeader>
              <CardTitle>{b.name}</CardTitle>
              <CardDescription>
                {b.skus} product{b.skus === 1 ? "" : "s"} on {b.pages} page{b.pages === 1 ? "" : "s"}
              </CardDescription>
            </CardHeader>
            <CardContent className="flex flex-col gap-3">
              <ScoreBadge score={b.score} />
              <dl className="grid grid-cols-2 gap-2 text-sm">
                <dt className="text-muted-foreground">Open issues</dt>
                <dd className="text-right tabular-nums">{b.unresolved}</dd>
                <dt className="text-muted-foreground">Per product</dt>
                <dd className="text-right tabular-nums">{b.issues_per_product}</dd>
              </dl>
            </CardContent>
          </Card>
        ))}
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Consistency score</CardTitle>
            <CardDescription>Out of 100. Higher means pages match the approved claims.</CardDescription>
          </CardHeader>
          <CardContent>
            <BarListChart data={c.brands.map((b) => ({ label: b.name, value: b.score ?? 0 }))} valueName="Score" labelWidth={90} />
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Open issues per product</CardTitle>
            <CardDescription>Lower is better. Adjusts for brands that monitor more products.</CardDescription>
          </CardHeader>
          <CardContent>
            <BarListChart
              data={c.brands.map((b) => ({ label: b.name, value: b.issues_per_product }))}
              valueName="Issues per product"
              labelWidth={90}
            />
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Where each brand is consistent</CardTitle>
          <CardDescription>
            Share of pages where each type of claim matches the approved version. Darker means more consistent.
          </CardDescription>
        </CardHeader>
        <CardContent className="overflow-x-auto">
          <table className="w-full min-w-[480px] border-separate border-spacing-1 text-sm">
            <thead>
              <tr>
                <th className="text-left text-xs font-medium text-muted-foreground">Claim type</th>
                {c.brands.map((b) => (
                  <th key={b.id} className="text-left text-xs font-medium text-muted-foreground">
                    {b.name}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {c.fields.map((f) => (
                <tr key={f}>
                  <th scope="row" className="pr-2 text-left font-medium">
                    {FIELD_LABEL[f]}
                  </th>
                  {c.brands.map((b) => {
                    const h = b.heatmap[f];
                    const pct = h.consistent_pct;
                    return (
                      <td
                        key={b.id}
                        className="h-14 min-w-28 rounded-md ring-1 ring-border ring-inset"
                        style={{
                          background:
                            pct === null ? undefined : `color-mix(in oklab, var(--series-1) ${Math.max(6, pct)}%, transparent)`,
                        }}
                      >
                        <div className="flex h-full flex-col items-start justify-center gap-0.5 px-2">
                          <span className="rounded bg-background/85 px-1 text-sm font-medium tabular-nums">
                            {pct === null ? "n/a" : `${pct}%`}
                          </span>
                          <span className="rounded bg-background/70 px-1 text-[11px] text-muted-foreground">
                            {h.checked ? `${h.checked - h.with_issues} of ${h.checked} pages` : "nothing to compare"}
                          </span>
                        </div>
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Claims coverage</CardTitle>
          <CardDescription>What each brand has approved, and what its pages claim without approval (dashed).</CardDescription>
        </CardHeader>
        <CardContent className="overflow-x-auto">
          <table className="w-full min-w-[560px] text-sm">
            <thead>
              <tr className="border-b">
                <th className="py-2 text-left text-xs font-medium text-muted-foreground">Claim type</th>
                {c.brands.map((b) => (
                  <th key={b.id} className="py-2 text-left text-xs font-medium text-muted-foreground">
                    {b.name}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {cats.map((cat) => (
                <tr key={cat} className="border-b last:border-0">
                  <th scope="row" className="py-3 pr-3 text-left align-top font-medium">
                    {c.categories[cat]}
                  </th>
                  {c.brands.map((b) => (
                    <td key={b.id} className="py-3 pr-3 align-top">
                      <ul className="flex flex-wrap gap-1.5">
                        {b.approved[cat].map((x) => (
                          <li key={x} className="rounded-md border px-1.5 py-0.5 text-xs">
                            {x}
                          </li>
                        ))}
                        {b.unapproved_on_pages[cat].map((x) => (
                          <li
                            key={`u-${x}`}
                            className="rounded-md border border-dashed border-critical/60 px-1.5 py-0.5 text-xs"
                            title="Seen on a page but not approved"
                          >
                            {x} <span className="text-muted-foreground">· not approved</span>
                          </li>
                        ))}
                        {!b.approved[cat].length && !b.unapproved_on_pages[cat].length && (
                          <li className="text-xs text-muted-foreground">None</li>
                        )}
                      </ul>
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </CardContent>
      </Card>
    </div>
  );
}
