import { BellOff } from "lucide-react";
import type { Metadata } from "next";
import { Suspense } from "react";
import { AlertsList, type AlertItem } from "@/components/alerts-list";
import { RunButton } from "@/components/audit/audit-actions";
import { EmptyState, LoadingBlock } from "@/components/common";
import { PageHeader } from "@/components/page-header";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { serverGet } from "@/lib/api";
import { brandParam, type SP } from "@/lib/params";

export const metadata: Metadata = { title: "AEO alerts" };

const RULES = [
  ["Score drop", "One of your brands' AEO score falls 3 points or more week on week (5 or more on a single engine)."],
  ["Competitor overtaking", "A competitor's AEO score moves above one of your brands, overall or on one engine."],
  ["Lost recommendation", "On a best-of or problem-led prompt, your brand's recommendation rate falls 20 points or more from at least 30%."],
  ["New wrong fact", "AI answers state a wrong product fact this week that no earlier answer stated."],
];

export default function AeoAlertsPage({ searchParams }: PageProps<"/aeo/alerts">) {
  return (
    <>
      <PageHeader
        title="AEO alerts"
        description="Changes in how AI assistants treat your brands, from comparing the latest week of answers with the week before."
        actions={<RunButton path="/aeo/alerts/evaluate" label="Check now" ok="AEO alerts checked" />}
      />
      <div className="grid gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <Suspense fallback={<LoadingBlock rows={3} />}>
            <List searchParams={searchParams} />
          </Suspense>
        </div>
        <Card className="h-fit">
          <CardHeader>
            <CardTitle>What raises an alert</CardTitle>
            <CardDescription>Checked after every AI run, and when you click Check now. They also appear in the bell and on Alerts.</CardDescription>
          </CardHeader>
          <CardContent>
            <dl className="flex flex-col gap-3 text-sm">
              {RULES.map(([name, rule]) => (
                <div key={name}>
                  <dt className="font-medium">{name}</dt>
                  <dd className="text-muted-foreground">{rule}</dd>
                </div>
              ))}
            </dl>
          </CardContent>
        </Card>
      </div>
    </>
  );
}

async function List({ searchParams }: { searchParams: Promise<SP> }) {
  const sp = await searchParams;
  const data = await serverGet<{ unread: number; items: AlertItem[] }>("/alerts", { brand_id: brandParam(sp), kind_prefix: "aeo_" });
  if (data.items.length === 0)
    return (
      <EmptyState title="No AEO alerts" icon={BellOff}>
        Nothing changed enough week on week. Alerts appear here after AI runs.
      </EmptyState>
    );
  return <AlertsList items={data.items} unread={data.unread} kindPrefix="aeo_" />;
}
