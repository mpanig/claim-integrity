import { ArrowDownRight, ArrowUpRight, Download, Minus } from "lucide-react";
import type { Metadata } from "next";
import { Suspense } from "react";
import { DemoBadge, EmptyState, LoadingBlock } from "@/components/common";
import { PageHeader } from "@/components/page-header";
import { PrintButton } from "@/components/print-button";
import { ScoreBadge, SeverityBadge, StatusBadge, VerdictBadge } from "@/components/status";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { serverGet } from "@/lib/api";
import { shortDate } from "@/lib/format";
import { FIELD_LABEL } from "@/lib/labels";
import { brandParam, type SP } from "@/lib/params";
import type { Field, Status, Verdict } from "@/lib/types";

export const metadata: Metadata = { title: "Reports" };

interface Report {
  brand: { id: number; name: string };
  period: { start: string; end: string };
  demo: boolean;
  score: { now: number | null; last_week: number | null; change: number | null };
  unresolved: number;
  new_issues: number;
  fixes_verified: number;
  in_progress: number;
  top_issues: { id: number; sku_name: string; page: string; field: Field; verdict: Verdict; severity: number; status: Status; value: string }[];
  products: { id: number; name: string; score: number | null; change: number | null; unresolved: number }[];
}

export default function ReportsPage({ searchParams }: PageProps<"/reports">) {
  return (
    <Suspense fallback={<LoadingBlock rows={3} />}>
      <Reports searchParams={searchParams} />
    </Suspense>
  );
}

function Change({ value }: { value: number | null }) {
  if (value === null) return <span className="text-xs text-muted-foreground">no data for last week</span>;
  const Icon = value > 0 ? ArrowUpRight : value < 0 ? ArrowDownRight : Minus;
  return (
    <span className="inline-flex items-center gap-0.5 text-xs text-muted-foreground">
      <Icon className={value > 0 ? "size-3.5 text-good" : value < 0 ? "size-3.5 text-critical" : "size-3.5"} />
      {value > 0 ? `+${value}` : value} vs last week
    </span>
  );
}

function Headline({ r }: { r: Report }) {
  const parts = [`Score ${r.score.now ?? "–"}/100`];
  const c = r.score.change;
  if (c !== null) parts[0] += c > 0 ? ` (up ${c})` : c < 0 ? ` (down ${-c})` : " (unchanged)";
  parts.push(`${r.new_issues} new issue${r.new_issues === 1 ? "" : "s"} found`);
  parts.push(`${r.fixes_verified} fix${r.fixes_verified === 1 ? "" : "es"} verified`);
  parts.push(`${r.unresolved} still open`);
  return <p className="text-sm">{parts.join(" · ")}.</p>;
}

async function Reports({ searchParams }: { searchParams: Promise<SP> }) {
  const sp = await searchParams;
  const brand_id = brandParam(sp);
  const { reports } = await serverGet<{ reports: Report[] }>("/reports/weekly", { brand_id });
  const csvHref = `/api/reports/issues.csv${brand_id ? `?brand_id=${brand_id}` : ""}`;

  return (
    <>
      <PageHeader
        title="Weekly report"
        description={
          reports[0]
            ? `Week of ${shortDate(reports[0].period.start)} to ${shortDate(reports[0].period.end)}. Share it as a PDF or export every open issue to a spreadsheet.`
            : "A weekly summary per brand."
        }
        actions={
          <>
            <a href={csvHref} download className="inline-flex h-8 items-center gap-1.5 rounded-lg border px-2.5 text-sm font-medium hover:bg-muted">
              <Download className="size-4" /> Export issues (CSV)
            </a>
            <PrintButton />
          </>
        }
      />
      {reports.length === 0 && <EmptyState title="No brands yet">Add a product to start getting reports.</EmptyState>}
      {reports.map((r, i) => (
        <section key={r.brand.id} className={`flex flex-col gap-4 ${i > 0 ? "border-t pt-6 print:break-before-page" : ""}`}>
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-xl font-semibold tracking-tight">{r.brand.name}</h2>
            {r.demo && <DemoBadge />}
          </div>
          <Headline r={r} />
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-5">
            <Card className="break-inside-avoid">
              <CardHeader>
                <CardDescription>Consistency score</CardDescription>
                <CardTitle className="text-3xl">{r.score.now ?? "–"}</CardTitle>
              </CardHeader>
              <CardContent>
                <Change value={r.score.change} />
              </CardContent>
            </Card>
            <Metric label="Open issues" value={r.unresolved} />
            <Metric label="New this week" value={r.new_issues} />
            <Metric label="Fixes verified" value={r.fixes_verified} />
            <Metric label="Being fixed" value={r.in_progress} />
          </div>
          <div className="grid gap-4 lg:grid-cols-2">
            <Card className="break-inside-avoid">
              <CardHeader>
                <CardTitle>Top issues</CardTitle>
              </CardHeader>
              <CardContent>
                {r.top_issues.length === 0 ? (
                  <p className="text-sm text-muted-foreground">No open issues.</p>
                ) : (
                  <ul className="flex flex-col divide-y">
                    {r.top_issues.map((x) => (
                      <li key={x.id} className="flex flex-col gap-1 py-2">
                        <div className="flex flex-wrap items-center gap-1.5">
                          <VerdictBadge verdict={x.verdict} />
                          <SeverityBadge severity={x.severity} />
                          <StatusBadge status={x.status} />
                        </div>
                        <span className="text-sm font-medium">
                          {FIELD_LABEL[x.field]} on {x.page}
                        </span>
                        <span className="truncate text-xs text-muted-foreground">
                          {x.value} · {x.sku_name}
                        </span>
                      </li>
                    ))}
                  </ul>
                )}
              </CardContent>
            </Card>
            <Card className="break-inside-avoid">
              <CardHeader>
                <CardTitle>Products</CardTitle>
              </CardHeader>
              <CardContent>
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Product</TableHead>
                      <TableHead>Score</TableHead>
                      <TableHead className="text-right">Open</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {r.products.map((p) => (
                      <TableRow key={p.id}>
                        <TableCell className="max-w-56 truncate">{p.name}</TableCell>
                        <TableCell>
                          <div className="flex flex-col items-start gap-0.5">
                            <ScoreBadge score={p.score} />
                            <Change value={p.change} />
                          </div>
                        </TableCell>
                        <TableCell className="text-right tabular-nums">{p.unresolved}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </CardContent>
            </Card>
          </div>
        </section>
      ))}
    </>
  );
}

function Metric({ label, value }: { label: string; value: number }) {
  return (
    <Card className="break-inside-avoid">
      <CardHeader>
        <CardDescription>{label}</CardDescription>
        <CardTitle className="text-3xl">{value}</CardTitle>
      </CardHeader>
    </Card>
  );
}
