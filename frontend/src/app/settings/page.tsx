import { Bot, Clock, KeyRound, Mail, Server } from "lucide-react";
import type { Metadata } from "next";
import { Suspense } from "react";
import { CarryLink, LoadingBlock, TimeAgo } from "@/components/common";
import { type Branding, BrandingForm } from "@/components/branding-form";
import { PageHeader } from "@/components/page-header";
import { Pill } from "@/components/status";
import { TeamManager } from "@/components/team-manager";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { serverGet } from "@/lib/api";
import type { EngineStatus, PlannedEngine } from "@/lib/ai";
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
            <Suspense fallback={<Row icon={Bot} label="AI engines" status={<Pill tone="neutral">Checking…</Pill>} />}>
              <EngineRows />
            </Suspense>
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
        <Suspense fallback={<LoadingBlock rows={1} />}>
          <JobsCard />
        </Suspense>
        <Card id="branding" className="xl:col-span-2">
          <CardHeader>
            <CardTitle>Report branding</CardTitle>
            <CardDescription>White-label the weekly report and its PDF: your logo, colours, title and footer.</CardDescription>
          </CardHeader>
          <CardContent>
            <Suspense fallback={<LoadingBlock rows={1} />}>
              <BrandingLoader />
            </Suspense>
          </CardContent>
        </Card>
      </div>
    </>
  );
}

interface Jobs {
  check_interval_hours: number;
  jobs: { name: string; label: string; last_started_at: string | null; last_status: string | null; last_detail: Record<string, unknown> | null }[];
  scheduled_plans: { id: number; name: string; schedule: string; last_run_at: string | null }[];
}

async function JobsCard() {
  const j = await serverGet<Jobs>("/jobs");
  const never = j.jobs.every((x) => !x.last_started_at);
  return (
    <Card className="h-fit">
      <CardHeader>
        <CardTitle>Background jobs</CardTitle>
        <CardDescription>
          Products are re-checked every {j.check_interval_hours} hours; each check adds a point to the score trend. Saved AI plans run on their schedule.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-3 text-sm">
        {j.jobs.map((job) => (
          <div key={job.name} className="flex items-center gap-2">
            <span className="flex-1">{job.label}</span>
            {job.last_status ? (
              <Pill tone={job.last_status === "done" ? "good" : job.last_status === "failed" ? "critical" : "warning"}>
                {job.last_status} · <TimeAgo iso={job.last_started_at} />
              </Pill>
            ) : (
              <Pill tone="neutral">Never run</Pill>
            )}
          </div>
        ))}
        {j.scheduled_plans.length > 0 && (
          <p className="text-xs text-muted-foreground">
            Scheduled AI plans: {j.scheduled_plans.map((p) => `${p.name} (${p.schedule})`).join(", ")}
          </p>
        )}
        {never && (
          <p className="text-xs text-muted-foreground">
            Start the worker next to the API with <code>uv run python -m app.worker</code>, or run one pass from cron with <code>--once</code>.
          </p>
        )}
      </CardContent>
    </Card>
  );
}

async function EngineRows() {
  const [engines, planned] = await Promise.all([serverGet<EngineStatus[]>("/ai/engines"), serverGet<PlannedEngine[]>("/ai/engines/planned")]);
  return (
    <>
      {engines.map((e) => (
        <Row
          key={e.engine}
          icon={Bot}
          label={
            <>
              {e.label} <span className="text-xs text-muted-foreground">({e.env_key})</span>
            </>
          }
          status={<Pill tone={e.status === "live" ? "good" : "neutral"}>{e.status === "live" ? "Live" : "Key missing"}</Pill>}
        />
      ))}
      {planned.map((p) => (
        <Row
          key={p.engine}
          icon={Clock}
          label={
            <span title={p.how}>
              {p.label} <span className="text-xs text-muted-foreground">({p.env_key})</span>
            </span>
          }
          status={<Pill tone="neutral">{p.key_set ? "Key set, connector coming" : "Planned"}</Pill>}
        />
      ))}
    </>
  );
}

async function BrandingLoader() {
  return <BrandingForm initial={await serverGet<Branding>("/reports/branding")} />;
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
