import { Bot, KeyRound, Mail, Server } from "lucide-react";
import type { Metadata } from "next";
import { Suspense } from "react";
import { CarryLink, LoadingBlock } from "@/components/common";
import { PageHeader } from "@/components/page-header";
import { Pill } from "@/components/status";
import { TeamManager } from "@/components/team-manager";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { serverGet } from "@/lib/api";
import type { Team } from "@/lib/team";
import type { Brand } from "@/lib/types";

export const metadata: Metadata = { title: "Settings" };

export default function SettingsPage() {
  return (
    <>
      <PageHeader title="Settings" description="Your team, their roles, and how the workspace is connected." />
      <div className="grid gap-6 xl:grid-cols-3">
        <Card className="xl:col-span-2">
          <CardHeader>
            <CardTitle>Team</CardTitle>
            <CardDescription>
              People who can own issues and tasks. Owner menus across the app use this list. Roles are labels for now:
              nobody signs in yet.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Suspense fallback={<LoadingBlock rows={2} />}>
              <TeamSection />
            </Suspense>
          </CardContent>
        </Card>
        <Card className="h-fit">
          <CardHeader>
            <CardTitle>Workspace</CardTitle>
            <CardDescription>What is connected today.</CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-3 text-sm">
            <Row icon={Server} label="Claim data" status={<Pill tone="good">Connected</Pill>} />
            <Row icon={KeyRound} label="Sign-in and permissions" status={<Pill tone="neutral">Not set up</Pill>} />
            <Row icon={Bot} label="AI assistants" status={<Pill tone="neutral">Not connected</Pill>} />
            <Row
              icon={Mail}
              label={
                <CarryLink href="/alerts" className="underline-offset-4 hover:underline">
                  Email and Slack alerts
                </CarryLink>
              }
              status={<Pill tone="neutral">Not connected</Pill>}
            />
            <p className="text-xs text-muted-foreground">
              Everyone currently acts as “Demo CMO” in the activity history until sign-in is added.
            </p>
          </CardContent>
        </Card>
      </div>
    </>
  );
}

async function TeamSection() {
  const [team, brands] = await Promise.all([serverGet<Team>("/team"), serverGet<Brand[]>("/brands")]);
  return <TeamManager team={team} brands={brands} />;
}

function Row({ icon: Icon, label, status }: { icon: React.ComponentType<{ className?: string }>; label: React.ReactNode; status: React.ReactNode }) {
  return (
    <div className="flex items-center gap-2">
      <Icon className="size-4 text-muted-foreground" />
      <span className="flex-1">{label}</span>
      {status}
    </div>
  );
}
