import type { Metadata } from "next";
import { Suspense } from "react";
import { AiTabs } from "@/components/ai/ai-tabs";
import { PlanBuilder } from "@/components/ai/plan-builder";
import { LoadingBlock, TimeAgo } from "@/components/common";
import { PageHeader } from "@/components/page-header";
import { Pill } from "@/components/status";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import type { AiRunRow, EngineStatus, Library, PlanConfig } from "@/lib/ai";
import { serverGet } from "@/lib/api";

export const metadata: Metadata = { title: "AI test plan" };

export default function PlanPage() {
  return (
    <>
      <PageHeader title="AI visibility" description="Choose what to ask, of which AI engines, as whom and from where; see the cost; then run it once or on a schedule." />
      <AiTabs />
      <Suspense fallback={<LoadingBlock rows={4} />}>
        <Plan />
      </Suspense>
    </>
  );
}

async function Plan() {
  const [lib, engines, saved, runs] = await Promise.all([
    serverGet<Library>("/ai/library"),
    serverGet<EngineStatus[]>("/ai/engines"),
    serverGet<{ id: number; name: string; config: PlanConfig; budget_usd: number; schedule: string; last_run_at: string | null }[]>("/ai/configs"),
    serverGet<AiRunRow[]>("/ai/runs"),
  ]);
  return (
    <div className="flex flex-col gap-6">
      <PlanBuilder lib={lib} engines={engines} saved={saved} />
      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Saved plans</CardTitle>
            <CardDescription>Scheduled plans run automatically when `python -m app.ai.schedule` is run by cron (for example hourly).</CardDescription>
          </CardHeader>
          <CardContent>
            <ul className="flex flex-col divide-y text-sm">
              {saved.map((s) => (
                <li key={s.id} className="flex flex-wrap items-center justify-between gap-2 py-2">
                  <span className="font-medium">{s.name}</span>
                  <span className="text-muted-foreground">
                    {s.schedule === "none" ? "manual" : s.schedule} · budget ${s.budget_usd} · last run <TimeAgo iso={s.last_run_at} />
                  </span>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Recent runs</CardTitle>
          </CardHeader>
          <CardContent>
            {runs.length === 0 ? (
              <p className="text-sm text-muted-foreground">No runs yet.</p>
            ) : (
              <ul className="flex flex-col divide-y text-sm">
                {runs.map((r) => (
                  <li key={r.id} className="flex flex-col gap-1 py-2">
                    <span className="flex flex-wrap items-center gap-2">
                      <span className="font-medium">Run {r.id}</span>
                      <Pill tone={r.status === "done" ? "good" : r.status === "running" ? "warning" : "serious"}>{r.status}</Pill>
                      {r.is_demo && <Pill tone="serious">demo</Pill>}
                      <span className="text-muted-foreground">
                        {r.done_calls}/{r.planned_calls} answers · ${r.cost_usd.toFixed(2)} of ${r.budget_usd.toFixed(2)} · analysed by {r.analyser ?? "–"} · <TimeAgo iso={r.started_at} />
                      </span>
                    </span>
                    {r.skipped.length > 0 && <span className="text-xs text-muted-foreground">Skipped: {r.skipped.map((s) => `${s.engine} (${s.reason})`).join(", ")}</span>}
                    {r.errors.length > 0 && <span className="text-xs text-muted-foreground">Last error: {r.errors[r.errors.length - 1].error}</span>}
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
