import { CircleAlert, Info } from "lucide-react";
import { DailyLines } from "@/components/ai/ai-charts";
import { DeleteUpload, LogUpload } from "@/components/aeo/log-upload";
import { DemoBadge } from "@/components/common";
import { Pill } from "@/components/status";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

export interface CrawlerData {
  demo: boolean;
  uploads: { id: number; filename: string; uploaded_at: string; lines: number; matched: number; skipped: number; first_day: string | null; last_day: string | null; is_demo: boolean }[];
  total: number;
  bots: { bot: string; company: string; purpose: string; hits: number; errors: number; pages: number; last_seen: string }[];
  series: Record<string, string | number>[];
  series_bots: string[];
  pages: { path: string; hits: number; bots: Record<string, number> }[];
  status: Record<string, number>;
  errors: { path: string; status: number; hits: number; bots: string[] }[];
  not_crawled: string[];
  known_bots: { bot: string; company: string; purpose: string }[];
}

function Stat({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <div className="rounded-xl border p-4">
      <p className="text-sm text-muted-foreground">{label}</p>
      <p className="text-2xl font-semibold tabular-nums">{value}</p>
      {note && <p className="text-xs text-muted-foreground">{note}</p>}
    </div>
  );
}

export function CrawlerActivity({ data }: { data: CrawlerData }) {
  const errors = (data.status["4xx"] ?? 0) + (data.status["5xx"] ?? 0);
  const userFetch = data.bots.filter((b) => b.purpose === "user fetch").reduce((s, b) => s + b.hits, 0);
  return (
    <>
      <Card id="crawler-logs">
        <CardHeader>
          <CardTitle className="flex flex-wrap items-center gap-2">AI crawler logs {data.demo && <DemoBadge />}</CardTitle>
          <CardDescription>
            Upload your web server access log to see which AI bots read your site. Only AI-bot counts per day, page and status
            are kept: no IP addresses, no raw lines. Demo data shows until your first upload.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <LogUpload
            path="/aeo/crawlers/upload"
            label="Upload access log"
            accept=".log,.txt,.csv,text/plain,text/csv"
            hint="Apache/Nginx combined log format, or CSV with time, path, status and user_agent columns. Up to 50 MB."
          />
          {data.uploads.length > 0 && (
            <ul className="flex flex-col gap-1 text-sm">
              {data.uploads.map((u) => (
                <li key={u.id} className="flex flex-wrap items-center gap-2">
                  <span className="font-medium">{u.filename}</span>
                  <span className="text-muted-foreground">
                    {u.first_day} to {u.last_day} · {u.matched} AI-bot requests in {u.lines} lines
                    {u.skipped ? ` · ${u.skipped} unreadable` : ""}
                  </span>
                  {u.is_demo ? <DemoBadge /> : <DeleteUpload path={`/aeo/crawlers/uploads/${u.id}`} name={u.filename} />}
                </li>
              ))}
            </ul>
          )}
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Stat label="AI bot requests" value={data.total.toLocaleString()} note="Last 28 days of the log" />
            <Stat label="Bots seen" value={String(data.bots.length)} note={`${data.known_bots.length} recognised`} />
            <Stat label="Fetched for a user" value={userFetch.toLocaleString()} note="ChatGPT-User, Claude-User, Perplexity-User: a person asked" />
            <Stat label="Errors served to bots" value={data.total ? `${Math.round((errors / data.total) * 100)}%` : "–"} note={`${errors} requests got 4xx/5xx`} />
          </div>
          {data.series.length > 0 && (
            <section className="flex flex-col gap-2">
              <h3 className="text-sm font-medium">Requests per day</h3>
              <DailyLines data={data.series} keys={data.series_bots} unit="requests" />
            </section>
          )}
        </CardContent>
      </Card>

      <div className="flex flex-col gap-4">
        <Card>
          <CardHeader>
            <CardTitle className="flex flex-wrap items-center gap-2">By bot {data.demo && <DemoBadge />}</CardTitle>
            <CardDescription>Recognised by user agent only (it can be faked; IPs are not checked).</CardDescription>
          </CardHeader>
          <CardContent className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Bot</TableHead>
                  <TableHead>Purpose</TableHead>
                  <TableHead className="text-right">Requests</TableHead>
                  <TableHead className="text-right">Pages</TableHead>
                  <TableHead className="text-right">Errors</TableHead>
                  <TableHead className="text-right">Last seen</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.bots.map((b) => (
                  <TableRow key={b.bot}>
                    <TableCell className="font-medium">
                      {b.bot} <span className="text-xs font-normal text-muted-foreground">{b.company}</span>
                    </TableCell>
                    <TableCell className="text-muted-foreground">{b.purpose}</TableCell>
                    <TableCell className="text-right tabular-nums">{b.hits}</TableCell>
                    <TableCell className="text-right tabular-nums">{b.pages}</TableCell>
                    <TableCell className="text-right tabular-nums">{b.errors ? <span className="text-critical">{b.errors}</span> : 0}</TableCell>
                    <TableCell className="text-right tabular-nums">{b.last_seen}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex flex-wrap items-center gap-2">Most-read pages {data.demo && <DemoBadge />}</CardTitle>
            <CardDescription>Pages AI bots request most, and which bots.</CardDescription>
          </CardHeader>
          <CardContent className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Page</TableHead>
                  <TableHead className="text-right">Requests</TableHead>
                  <TableHead>Top bots</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.pages.slice(0, 10).map((p) => (
                  <TableRow key={p.path}>
                    <TableCell className="max-w-72 truncate font-medium" title={p.path}>
                      {p.path}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">{p.hits}</TableCell>
                    <TableCell className="text-xs text-muted-foreground">
                      {Object.entries(p.bots)
                        .slice(0, 3)
                        .map(([b, n]) => `${b} ${n}`)
                        .join(" · ")}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="flex flex-wrap items-center gap-2">Errors served to AI bots {data.demo && <DemoBadge />}</CardTitle>
            <CardDescription>A bot that gets an error can&apos;t read the page. 403s are often a firewall or bot blocker.</CardDescription>
          </CardHeader>
          <CardContent>
            {data.errors.length === 0 ? (
              <p className="text-sm text-muted-foreground">No errors.</p>
            ) : (
              <ul className="flex flex-col gap-2 text-sm">
                {data.errors.slice(0, 8).map((e) => (
                  <li key={`${e.path}|${e.status}`} className="flex flex-wrap items-center gap-2">
                    <Pill tone={e.status >= 500 ? "critical" : "serious"}>{e.status}</Pill>
                    <span className="font-medium">{e.path}</span>
                    <span className="text-muted-foreground">
                      {e.hits} {e.hits === 1 ? "request" : "requests"} · {e.bots.join(", ")}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <CircleAlert className="size-4" /> Key pages no AI bot has read
            </CardTitle>
            <CardDescription>Pages on your audit list that no AI crawler requested in the log.</CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-3">
            {data.not_crawled.length === 0 ? (
              <p className="text-sm text-muted-foreground">Every audited page was read by at least one AI bot.</p>
            ) : (
              <ul className="list-disc pl-5 text-sm">
                {data.not_crawled.map((p) => (
                  <li key={p}>{p}</li>
                ))}
              </ul>
            )}
            <p className="flex gap-1.5 text-xs text-muted-foreground">
              <Info className="mt-0.5 size-3.5 shrink-0" />
              The log may be from one site only. Google-Extended and Applebot-Extended are robots.txt settings, not crawlers:
              Google and Apple fetch as Googlebot and Applebot, so those names never appear in logs.
            </p>
          </CardContent>
        </Card>
      </div>
    </>
  );
}
