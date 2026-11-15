import { BellOff, Mail, MessageSquare } from "lucide-react";
import type { Metadata } from "next";
import { Suspense } from "react";
import { AlertsList, type AlertItem } from "@/components/alerts-list";
import { EmptyState, LoadingBlock } from "@/components/common";
import { PageHeader } from "@/components/page-header";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { serverGet } from "@/lib/api";
import { brandParam, type SP } from "@/lib/params";

export const metadata: Metadata = { title: "Alerts" };

export default function AlertsPage({ searchParams }: PageProps<"/alerts">) {
  return (
    <>
      <PageHeader
        title="Alerts"
        description="Raised by each check: every new unapproved or self-contradicting claim, and any product whose score drops 5 points or more."
      />
      <div className="grid gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <Suspense fallback={<LoadingBlock rows={3} />}>
            <Alerts searchParams={searchParams} />
          </Suspense>
        </div>
        <NotificationSettings />
      </div>
    </>
  );
}

async function Alerts({ searchParams }: { searchParams: Promise<SP> }) {
  const sp = await searchParams;
  const data = await serverGet<{ unread: number; items: AlertItem[] }>("/alerts", { brand_id: brandParam(sp) });
  if (data.items.length === 0)
    return (
      <EmptyState title="No alerts" icon={BellOff}>
        You&apos;ll be alerted here when a check finds a high-risk issue or a score drops.
      </EmptyState>
    );
  return <AlertsList items={data.items} unread={data.unread} />;
}

function NotificationSettings() {
  // TODO(notify): save per-user settings and deliver by email / Slack.
  const rows = [
    { id: "email-high", icon: Mail, label: "Email me new high-risk issues" },
    { id: "email-digest", icon: Mail, label: "Weekly email digest" },
    { id: "slack", icon: MessageSquare, label: "Post alerts to a Slack channel" },
  ];
  return (
    <Card className="h-fit">
      <CardHeader>
        <CardTitle>Notifications</CardTitle>
        <CardDescription>Email and Slack delivery are not connected yet. Alerts appear in the app only.</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        {rows.map(({ id, icon: Icon, label }) => (
          <div key={id} className="flex items-center gap-2 opacity-60">
            <Checkbox id={id} disabled />
            <Icon className="size-4 text-muted-foreground" />
            <Label htmlFor={id} className="font-normal">
              {label}
            </Label>
          </div>
        ))}
        <p className="text-xs text-muted-foreground">Coming soon: per-person settings for each team member.</p>
      </CardContent>
    </Card>
  );
}
