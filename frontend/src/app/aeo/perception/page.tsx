import { CircleDot, Info } from "lucide-react";
import type { Metadata } from "next";
import { Suspense } from "react";
import { AiFilters } from "@/components/ai/ai-filters";
import { PositioningEditor } from "@/components/aeo/positioning-editor";
import { DemoBadge, EmptyState, LoadingBlock } from "@/components/common";
import { PageHeader } from "@/components/page-header";
import { Pill } from "@/components/status";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { aiFilterParams, type Library, type Perception, pct } from "@/lib/ai";
import { serverGet } from "@/lib/api";
import type { SP } from "@/lib/params";
import { cn } from "@/lib/utils";

export const metadata: Metadata = { title: "AEO brand perception" };

export default function PerceptionPage({ searchParams }: PageProps<"/aeo/perception">) {
  return (
    <>
      <PageHeader
        title="Brand perception"
        description="What AI answers say each brand stands for, next to your competitors and to the positioning you want."
      />
      <Suspense fallback={<LoadingBlock rows={4} />}>
        <PerceptionView searchParams={searchParams} />
      </Suspense>
    </>
  );
}

const GAP_TEXT = {
  missing: "Intended, but AI rarely says it",
  unwanted: "AI says it often, and it hurts",
  unplanned: "AI says it often, not in your positioning",
} as const;

async function PerceptionView({ searchParams }: { searchParams: Promise<SP> }) {
  const sp = await searchParams;
  const [p, lib] = await Promise.all([serverGet<Perception>("/ai/perception", aiFilterParams(sp)), serverGet<Library>("/ai/library")]);
  const label = Object.fromEntries(p.attributes.map((a) => [a.key, a.label]));
  const brands = p.brands.filter((b) => b.answers > 0);
  const own = brands.filter((b) => b.is_own);
  return (
    <div className="flex flex-col gap-6">
      <AiFilters personas={lib.personas} regions={["US", "IN", "GB"]} />
      {p.answers === 0 ? (
        <EmptyState title="No answers for these filters">Run a test plan, or clear the filters.</EmptyState>
      ) : (
        <>
          <Card id="map">
            <CardHeader>
              <CardTitle className="flex flex-wrap items-center gap-2">Perception map {p.demo && <DemoBadge />}</CardTitle>
              <CardDescription>
                Share of answers naming each brand that also link it to the attribute (in the same sentence). Darker is more
                often; bold marks the brand that owns the attribute; <CircleDot className="inline size-3.5" /> marks your
                intended positioning. English wording only for now.
              </CardDescription>
            </CardHeader>
            <CardContent className="overflow-x-auto">
              <table className="w-full min-w-[720px] border-separate border-spacing-1 text-sm">
                <thead>
                  <tr>
                    <th className="text-left text-xs font-medium text-muted-foreground">Attribute</th>
                    {brands.map((b) => (
                      <th key={b.name} className="text-left text-xs font-medium text-muted-foreground">
                        {b.name}
                        {b.is_own && <span className="block font-normal">ours · n = {b.answers}</span>}
                        {!b.is_own && <span className="block font-normal">n = {b.answers}</span>}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {p.attributes.map((a) => (
                    <tr key={a.key}>
                      <th scope="row" className="pr-2 text-left font-medium whitespace-nowrap">
                        {a.label}
                        {a.polarity === "negative" && <span className="ml-1 text-xs font-normal text-critical">negative</span>}
                      </th>
                      {brands.map((b) => {
                        const r = b.attributes[a.key];
                        const intended = b.positioning.includes(a.key);
                        const tone = a.polarity === "negative" ? "var(--status-critical)" : "var(--series-1)";
                        return (
                          <td
                            key={b.name}
                            className={cn("h-10 min-w-20 rounded-md px-2 ring-1 ring-border ring-inset", intended && "ring-2 ring-foreground/60")}
                            style={{ background: r.rate ? `color-mix(in oklab, ${tone} ${Math.max(6, Math.round(r.rate * 90))}%, transparent)` : undefined }}
                            title={r.example ? `${r.k} of ${r.n} answers. e.g. “${r.example}”` : `${r.k} of ${r.n} answers`}
                          >
                            <span className={cn("inline-flex items-center gap-1 rounded bg-background/85 px-1 tabular-nums", p.leaders[a.key] === b.name && "font-semibold")}>
                              {intended && <CircleDot className="size-3" aria-label="intended" />}
                              {r.rate ? pct(r.rate) : "–"}
                            </span>
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </CardContent>
          </Card>

          <div className="grid gap-4 lg:grid-cols-2">
            {own.map((b) => (
              <Card key={b.name}>
                <CardHeader>
                  <CardTitle className="flex flex-wrap items-center gap-2">
                    {b.name}: positioning vs AI {p.demo && <DemoBadge />}
                  </CardTitle>
                  <CardDescription>
                    Gaps: intended attributes below {pct(p.thresholds.weak)} of answers, and others at {pct(p.thresholds.strong)} or more.
                  </CardDescription>
                </CardHeader>
                <CardContent className="flex flex-col gap-4">
                  {b.positioning.length === 0 ? (
                    <p className="flex items-center gap-1.5 text-sm text-muted-foreground">
                      <Info className="size-4" /> No intended positioning yet. Choose attributes below to see gaps.
                    </p>
                  ) : (
                    <ul className="flex flex-col gap-2">
                      {b.positioning.map((k) => {
                        const r = b.attributes[k];
                        const leaderName = p.leaders[k];
                        const leaderRate = p.brands.find((x) => x.name === leaderName)?.attributes[k].rate ?? 0;
                        // Only call out a rival that is strictly ahead (ties are shared).
                        const leader = leaderName && leaderName !== b.name && leaderRate > (r.rate ?? 0) ? leaderName : null;
                        return (
                          <li key={k} className="flex flex-col gap-1">
                            <div className="flex items-baseline justify-between gap-2 text-sm">
                              <span>{label[k]}</span>
                              <span className="tabular-nums text-muted-foreground">
                                {pct(r.rate ?? 0)}
                                {leader && ` · ${leader} leads with ${pct(leaderRate)}`}
                              </span>
                            </div>
                            <div className="h-2 rounded-full bg-muted" role="img" aria-label={`${label[k]}: ${pct(r.rate ?? 0)}`}>
                              <div
                                className={cn("h-2 rounded-full", (r.rate ?? 0) < p.thresholds.weak ? "bg-serious" : "bg-[var(--series-1)]")}
                                style={{ width: `${Math.max(2, Math.round((r.rate ?? 0) * 100))}%` }}
                              />
                            </div>
                          </li>
                        );
                      })}
                    </ul>
                  )}
                  {b.gaps.length > 0 && (
                    <ul className="flex flex-col gap-1.5">
                      {b.gaps.map((g) => (
                        <li key={g.attribute} className="flex flex-wrap items-center gap-2 text-sm">
                          <Pill tone={g.kind === "unwanted" ? "critical" : g.kind === "missing" ? "serious" : "neutral"}>{GAP_TEXT[g.kind]}</Pill>
                          {label[g.attribute]} · {pct(g.rate)}
                        </li>
                      ))}
                    </ul>
                  )}
                  {b.brand_id !== null && <PositioningEditor brandId={b.brand_id} brandName={b.name} attributes={p.attributes} initial={b.positioning} />}
                </CardContent>
              </Card>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
