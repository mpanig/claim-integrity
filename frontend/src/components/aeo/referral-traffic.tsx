import { Info, PlugZap } from "lucide-react";
import { DailyLines } from "@/components/ai/ai-charts";
import { BarListChart } from "@/components/charts/bar-list-chart";
import { DeleteUpload, LogUpload } from "@/components/aeo/log-upload";
import { DemoBadge } from "@/components/common";
import { Pill } from "@/components/status";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

export interface ReferralData {
  demo: boolean;
  uploads: { id: number; filename: string; uploaded_at: string; lines: number; matched: number; skipped: number; first_day: string | null; last_day: string | null; is_demo: boolean }[];
  ai_sessions: number;
  ai_share: number | null;
  ai_conversion_rate: number | null;
  other_conversion_rate: number | null;
  change_28d: number | null;
  sources: { source: string; sessions: number; conversions: number; conversion_rate: number | null; share_of_ai: number | null }[];
  series: Record<string, string | number>[];
  series_keys: string[];
  pages: { landing: string; sessions: number; sources: Record<string, number> }[];
  known_sources: { source: string; domains: string[] }[];
  ga4: { status: string; property_set: boolean };
}

const pct = (v: number | null, digits = 0) => (v === null ? "–" : `${(v * 100).toFixed(digits)}%`);

function Stat({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <div className="rounded-xl border p-4">
      <p className="text-sm text-muted-foreground">{label}</p>
      <p className="text-2xl font-semibold tabular-nums">{value}</p>
      {note && <p className="text-xs text-muted-foreground">{note}</p>}
    </div>
  );
}

export function ReferralTraffic({ data }: { data: ReferralData }) {
  const lift = data.ai_conversion_rate !== null && data.other_conversion_rate ? data.ai_conversion_rate / data.other_conversion_rate : null;
  return (
    <>
      <Card id="referrals">
        <CardHeader>
          <CardTitle className="flex flex-wrap items-center gap-2">AI referral traffic {data.demo && <DemoBadge />}</CardTitle>
          <CardDescription>
            Visits that arrive from AI assistants ({data.known_sources.map((s) => s.source).join(", ")}). Import a CSV from
            your analytics; demo data shows until your first import.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <LogUpload
            path="/aeo/referrals/upload"
            label="Import analytics CSV"
            accept=".csv,text/csv"
            hint="Columns: date, session source (or source / referrer), sessions; optional key events / conversions and landing page."
          />
          {data.uploads.length > 0 && (
            <ul className="flex flex-col gap-1 text-sm">
              {data.uploads.map((u) => (
                <li key={u.id} className="flex flex-wrap items-center gap-2">
                  <span className="font-medium">{u.filename}</span>
                  <span className="text-muted-foreground">
                    {u.first_day} to {u.last_day} · {u.matched.toLocaleString()} AI sessions
                    {u.skipped ? ` · ${u.skipped} rows unreadable` : ""}
                  </span>
                  {u.is_demo ? <DemoBadge /> : <DeleteUpload path={`/aeo/referrals/uploads/${u.id}`} name={u.filename} />}
                </li>
              ))}
            </ul>
          )}
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Stat label="AI sessions" value={data.ai_sessions.toLocaleString()} note={data.change_28d === null ? undefined : `${data.change_28d >= 0 ? "+" : ""}${pct(data.change_28d)} last 28 days vs the 28 before`} />
            <Stat label="Share of all sessions" value={pct(data.ai_share, 1)} note={data.ai_share === null ? "Include non-AI rows in the CSV to see this" : undefined} />
            <Stat label="AI conversion rate" value={pct(data.ai_conversion_rate, 1)} note={lift ? `${lift.toFixed(1)}× the rest of your traffic (${pct(data.other_conversion_rate, 1)})` : undefined} />
            <Stat label="Top assistant" value={data.sources[0]?.source ?? "–"} note={data.sources[0] ? `${pct(data.sources[0].share_of_ai)} of AI sessions` : undefined} />
          </div>
          {data.series.length > 0 && (
            <div className="grid gap-6 lg:grid-cols-5">
              <section className="flex flex-col gap-2 lg:col-span-3">
                <h3 className="text-sm font-medium">Sessions per week, by assistant (whole weeks)</h3>
                <DailyLines data={data.series} keys={data.series_keys} unit="sessions" />
              </section>
              <section className="flex flex-col gap-2 lg:col-span-2">
                <h3 className="text-sm font-medium">By assistant</h3>
                <BarListChart data={data.sources.map((s) => ({ label: s.source, value: s.sessions }))} valueName="Sessions" labelWidth={90} />
              </section>
            </div>
          )}
        </CardContent>
      </Card>

      <div className="grid gap-4 xl:grid-cols-3">
        <Card className="xl:col-span-2">
          <CardHeader>
            <CardTitle className="flex flex-wrap items-center gap-2">Landing pages from AI {data.demo && <DemoBadge />}</CardTitle>
            <CardDescription>Where AI assistants send people. These pages deserve the most accurate, answer-ready content.</CardDescription>
          </CardHeader>
          <CardContent className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Landing page</TableHead>
                  <TableHead className="text-right">Sessions</TableHead>
                  <TableHead>From</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.pages.slice(0, 10).map((p) => (
                  <TableRow key={p.landing}>
                    <TableCell className="max-w-80 truncate font-medium" title={p.landing}>
                      {p.landing}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">{p.sessions.toLocaleString()}</TableCell>
                    <TableCell className="text-xs text-muted-foreground">
                      {Object.entries(p.sources)
                        .map(([s, n]) => `${s} ${n}`)
                        .join(" · ")}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
        <Card id="ga4">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <PlugZap className="size-4" /> Google Analytics 4
            </CardTitle>
            <CardDescription>A direct GA4 connection is planned; for now, import a CSV export.</CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-3 text-sm">
            <div>
              <Pill tone="neutral">{data.ga4.status}</Pill>
            </div>
            <ol className="list-decimal pl-5 text-muted-foreground">
              <li>In GA4, open Reports › Acquisition › Traffic acquisition.</li>
              <li>Set the dimension to Session source, add Landing page as a secondary dimension.</li>
              <li>Choose the date range, then Share › Download file › CSV.</li>
              <li>Import it here.</li>
            </ol>
            <Button variant="outline" disabled title="Not built yet: needs a GA4 property ID and a service account">
              Connect GA4 (coming soon)
            </Button>
            <p className="flex gap-1.5 text-xs text-muted-foreground">
              <Info className="mt-0.5 size-3.5 shrink-0" />
              Some AI visits arrive without a referrer and show as direct traffic, so these numbers are a floor.
            </p>
          </CardContent>
        </Card>
      </div>
    </>
  );
}
