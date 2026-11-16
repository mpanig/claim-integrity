import { ArrowDownRight, ArrowUpRight, Minus } from "lucide-react";
import { ScoreTrend } from "@/components/ai/ai-charts";
import { BarListChart } from "@/components/charts/bar-list-chart";
import { DemoBadge } from "@/components/common";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { AEO_COMPONENT_LABEL, type AeoBrandScore, type AeoScore, pct } from "@/lib/ai";
import { SERIES } from "@/lib/chart-colors";
import { cn } from "@/lib/utils";

function Change({ value }: { value?: number }) {
  if (value === undefined) return null;
  const Icon = value > 0.5 ? ArrowUpRight : value < -0.5 ? ArrowDownRight : Minus;
  return (
    <span className={cn("inline-flex items-center gap-0.5 text-xs tabular-nums", value > 0.5 ? "text-good" : value < -0.5 ? "text-critical" : "text-muted-foreground")}>
      <Icon className="size-3.5" />
      {value > 0 ? "+" : ""}
      {value.toFixed(1)} vs last week
    </span>
  );
}

function Tile({ b, rank, leader }: { b: AeoBrandScore; rank: number; leader: AeoBrandScore }) {
  const gap = Math.round((b.score - leader.score) * 10) / 10;
  return (
    <div className="flex flex-col gap-1 rounded-xl border p-4">
      <p className="text-sm text-muted-foreground">
        {b.name} · #{rank} of brands
      </p>
      <p className="text-3xl font-semibold tabular-nums">{b.score.toFixed(1)}</p>
      <Change value={b.change} />
      <p className="text-xs text-muted-foreground">{gap === 0 ? "Leads the category" : `${Math.abs(gap).toFixed(1)} behind ${leader.name}`}</p>
    </div>
  );
}

/** AEO score: tiles for our brands, competitor benchmark, trend, engine breakdown, prominence. */
export function AeoScoreSection({ score }: { score: AeoScore }) {
  if (!score.brands.length) return null;
  const leader = score.brands[0];
  const own = score.brands.filter((b) => b.is_own);
  const rival = score.top_rival;
  const trendBrands = [...own.map((b) => b.name), ...(rival ? [rival.name] : [])];
  const colors = Object.fromEntries(trendBrands.map((b, i) => [b, SERIES[Math.min(i, SERIES.length - 1)]]));
  const weights = Object.entries(score.weights)
    .map(([k, w]) => `${AEO_COMPONENT_LABEL[k] ?? k} ${Math.round(w * 100)}%`)
    .join(" · ");
  const names = score.brands.map((b) => b.name);
  return (
    <>
      <Card id="score">
        <CardHeader>
          <CardTitle className="flex flex-wrap items-center gap-2">AEO score {score.demo && <DemoBadge />}</CardTitle>
          <CardDescription>
            One number, 0–100, for how well AI answers serve each brand, from {score.answers} answers. Made of: {weights}.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-6">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {own.map((b) => (
              <Tile key={b.name} b={b} rank={names.indexOf(b.name) + 1} leader={leader} />
            ))}
            {rival && <Tile b={rival} rank={names.indexOf(rival.name) + 1} leader={leader} />}
          </div>
          <div className="grid gap-6 lg:grid-cols-2">
            <section className="flex flex-col gap-2">
              <h3 className="text-sm font-medium">Competitor benchmark</h3>
              <BarListChart data={score.brands.map((b) => ({ label: b.is_own ? `${b.name} (ours)` : b.name, value: b.score }))} valueName="AEO score" labelWidth={130} />
            </section>
            <section className="flex flex-col gap-2">
              <h3 className="text-sm font-medium">Score by week</h3>
              <ScoreTrend trend={score.trend} brands={trendBrands} colors={colors} rivals={rival ? [rival.name] : []} />
            </section>
          </div>
        </CardContent>
      </Card>

      <div className="grid gap-4 xl:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="flex flex-wrap items-center gap-2">Score by engine {score.demo && <DemoBadge />}</CardTitle>
            <CardDescription>AEO score per brand on each AI engine. Darker is higher; the best brand on each engine is bold.</CardDescription>
          </CardHeader>
          <CardContent className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Brand</TableHead>
                  {score.by_engine.map((e) => (
                    <TableHead key={e.engine} className="text-right">
                      {e.label}
                    </TableHead>
                  ))}
                </TableRow>
              </TableHeader>
              <TableBody>
                {names.map((name) => (
                  <TableRow key={name}>
                    <TableCell className="font-medium">{name}</TableCell>
                    {score.by_engine.map((e) => {
                      const b = e.brands.find((x) => x.name === name);
                      const top = e.brands[0]?.name === name;
                      return (
                        <TableCell
                          key={e.engine}
                          className={cn("text-right tabular-nums", top && "font-semibold")}
                          style={b ? { background: `color-mix(in oklab, var(--series-1) ${Math.round(b.score * 0.6)}%, transparent)` } : undefined}
                        >
                          {b ? b.score.toFixed(1) : "–"}
                        </TableCell>
                      );
                    })}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>

        <Card id="prominence">
          <CardHeader>
            <CardTitle className="flex flex-wrap items-center gap-2">Prominence {score.demo && <DemoBadge />}</CardTitle>
            <CardDescription>
              How early and how much each brand is talked about. “Named first” is the share of answers where it is the first
              brand named; “first named at” is how far into the answer, on average, when it is named.
            </CardDescription>
          </CardHeader>
          <CardContent className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Brand</TableHead>
                  <TableHead className="text-right">Named first</TableHead>
                  <TableHead className="text-right">First named at</TableHead>
                  <TableHead className="text-right">Share of words</TableHead>
                  <TableHead className="text-right">Mentioned</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {score.brands.map((b) => (
                  <TableRow key={b.name}>
                    <TableCell className="font-medium">
                      {b.name}
                      {b.is_own && <span className="ml-1 text-xs text-muted-foreground">ours</span>}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">{pct(b.first_named)}</TableCell>
                    <TableCell className="text-right tabular-nums">{b.first_offset === null ? "–" : `${pct(b.first_offset)} in`}</TableCell>
                    <TableCell className="text-right tabular-nums">{pct(b.word_share)}</TableCell>
                    <TableCell className="text-right tabular-nums">{pct(b.components.mention)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      </div>
    </>
  );
}
