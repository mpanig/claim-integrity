import { Bot, PlugZap, Repeat } from "lucide-react";
import type { Metadata } from "next";
import { Suspense } from "react";
import { AiPromptForm, DeletePromptButton } from "@/components/ai-prompt-form";
import { BarListChart } from "@/components/charts/bar-list-chart";
import { DemoBadge, EmptyState, LoadingBlock, TimeAgo } from "@/components/common";
import { PageHeader } from "@/components/page-header";
import { VerdictBadge } from "@/components/status";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { serverGet } from "@/lib/api";
import { displayValue } from "@/lib/format";
import { FIELD_LABEL } from "@/lib/labels";
import { brandParam, type SP } from "@/lib/params";
import type { Field, Sku, Verdict } from "@/lib/types";

export const metadata: Metadata = { title: "AI visibility" };

interface AiOverview {
  configured: boolean;
  demo: boolean;
  prompts: { id: number; text: string; sku_id: number | null; sku_name: string | null; answers: number }[];
  answers: {
    id: number;
    prompt: string;
    sku_name: string | null;
    assistant: string;
    answer: string;
    asked_at: string;
    stated_facts: Record<string, string[] | string>;
    mentioned_brands: string[];
    findings: { field: Field; verdict: Verdict; severity: number; stated: unknown; approved: unknown; echoes: string[] }[];
    is_demo: boolean;
  }[];
  accuracy: { checked: number; with_issues: number };
  share_of_voice: { brand: string; mentions: number; share: number }[];
}

const FACT_LABEL: Record<string, string> = { ...FIELD_LABEL, contains: "Says it contains" };

export default function AiVisibilityPage({ searchParams }: PageProps<"/ai-visibility">) {
  return (
    <>
      <PageHeader
        title="AI visibility"
        description="What AI assistants tell shoppers about your products, and whether it matches your approved claims."
      />
      <Suspense fallback={<LoadingBlock rows={3} />}>
        <AiVisibility searchParams={searchParams} />
      </Suspense>
    </>
  );
}

function verdictSentence(f: AiOverview["answers"][number]["findings"][number]): string {
  const stated = displayValue(f.stated);
  switch (f.verdict) {
    case "outdated":
      return `Says it contains ${stated}, which is not in the current formula.`;
    case "risky":
      return `Claims "${stated}", which is not approved.`;
    case "drift":
      return `Says "${stated}" instead of "${displayValue(f.approved)}".`;
    default:
      return `${FIELD_LABEL[f.field]}: ${stated}`;
  }
}

async function AiVisibility({ searchParams }: { searchParams: Promise<SP> }) {
  const sp = await searchParams;
  const brand_id = brandParam(sp);
  const [a, skus] = await Promise.all([
    serverGet<AiOverview>("/ai-visibility", { brand_id }),
    serverGet<Sku[]>("/skus", { brand_id }),
  ]);

  return (
    <div className="flex flex-col gap-6">
      {!a.configured && (
        <Alert>
          <PlugZap />
          <AlertTitle>AI assistants aren&apos;t connected yet</AlertTitle>
          <AlertDescription>
            No assistant is being asked right now. You can already choose the questions to track below; they&apos;ll be
            asked automatically once assistant API keys are added.
            {a.demo && " The answers on this page are invented samples, marked Demo data."}
          </AlertDescription>
        </Alert>
      )}

      <div className="grid gap-4 sm:grid-cols-3">
        <Stat label="Prompts tracked" value={a.prompts.length} />
        <Stat label="Answers collected" value={a.answers.length} demo={a.demo} />
        <Stat
          label="Answers with wrong or unapproved facts"
          value={a.accuracy.checked ? `${a.accuracy.with_issues} of ${a.accuracy.checked}` : "–"}
          demo={a.demo}
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-5">
        <Card className="lg:col-span-3">
          <CardHeader>
            <CardTitle>Prompts to track</CardTitle>
            <CardDescription>Questions shoppers ask. Product-specific prompts are checked against that product&apos;s truth sheet.</CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-4">
            <AiPromptForm products={skus.map((s) => ({ id: s.id, name: s.name }))} />
            {a.prompts.length === 0 ? (
              <p className="text-sm text-muted-foreground">No prompts yet.</p>
            ) : (
              <ul className="flex flex-col divide-y">
                {a.prompts.map((p) => (
                  <li key={p.id} className="flex items-center gap-3 py-2">
                    <div className="min-w-0 flex-1">
                      <p className="text-sm">{p.text}</p>
                      <p className="text-xs text-muted-foreground">
                        {p.sku_name ?? "General question"} · {p.answers} answer{p.answers === 1 ? "" : "s"}
                      </p>
                    </div>
                    <DeletePromptButton id={p.id} />
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle className="flex flex-wrap items-center gap-2">Share of voice {a.demo && <DemoBadge />}</CardTitle>
            <CardDescription>How often each brand is mentioned across all answers.</CardDescription>
          </CardHeader>
          <CardContent>
            {a.share_of_voice.length ? (
              <BarListChart
                data={a.share_of_voice.map((s) => ({ label: s.brand, value: s.share }))}
                valueName="Share of mentions"
                unit="%"
                labelWidth={100}
              />
            ) : (
              <EmptyState title="No answers yet" icon={Bot} />
            )}
          </CardContent>
        </Card>
      </div>

      <section className="flex flex-col gap-3">
        <h2 className="flex items-center gap-2 font-medium">Answers {a.demo && <DemoBadge />}</h2>
        {a.answers.length === 0 ? (
          <EmptyState title="No answers yet" icon={Bot}>
            Answers appear here once AI assistants are connected and your prompts have been asked.
          </EmptyState>
        ) : (
          <div className="grid gap-4 lg:grid-cols-2">
            {a.answers.map((x) => (
              <Card key={x.id}>
                <CardHeader>
                  <CardDescription className="flex flex-wrap items-center gap-2">
                    {x.assistant} · <TimeAgo iso={x.asked_at} /> {x.is_demo && <DemoBadge />}
                  </CardDescription>
                  <CardTitle className="text-base">{x.prompt}</CardTitle>
                </CardHeader>
                <CardContent className="flex flex-col gap-3">
                  <blockquote className="rounded-lg bg-muted/60 p-3 text-sm leading-relaxed">{x.answer}</blockquote>
                  {Object.keys(x.stated_facts).length > 0 && (
                    <dl className="flex flex-col gap-1 text-xs">
                      {Object.entries(x.stated_facts).map(([k, v]) => (
                        <div key={k} className="flex gap-2">
                          <dt className="w-32 shrink-0 text-muted-foreground">{FACT_LABEL[k] ?? k}</dt>
                          <dd>{displayValue(v)}</dd>
                        </div>
                      ))}
                    </dl>
                  )}
                  {x.sku_name && x.findings.length === 0 && (
                    <p className="text-sm text-muted-foreground">Everything stated matches the approved claims.</p>
                  )}
                  {x.findings.length > 0 && (
                    <ul className="flex flex-col gap-2">
                      {x.findings.map((f, i) => (
                        <li key={i} className="flex flex-col gap-1 rounded-lg border p-2">
                          <VerdictBadge
                            verdict={f.verdict}
                            label={f.verdict === "outdated" ? "Outdated ingredient info" : undefined}
                          />
                          <span className="text-sm">{verdictSentence(f)}</span>
                          {f.echoes.length > 0 && (
                            <span className="flex items-center gap-1 text-xs text-muted-foreground">
                              <Repeat className="size-3.5" /> Repeats an open issue on {f.echoes.join(", ")}. Fixing that
                              page may fix this answer too.
                            </span>
                          )}
                        </li>
                      ))}
                    </ul>
                  )}
                  {x.mentioned_brands.length > 0 && (
                    <p className="text-xs text-muted-foreground">Mentions: {x.mentioned_brands.join(", ")}</p>
                  )}
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

function Stat({ label, value, demo }: { label: string; value: number | string; demo?: boolean }) {
  return (
    <Card>
      <CardHeader>
        <CardDescription className="flex flex-wrap items-center gap-2">
          {label} {demo && <DemoBadge />}
        </CardDescription>
      </CardHeader>
      <CardContent>
        <span className="text-3xl font-semibold tracking-tight">{value}</span>
      </CardContent>
    </Card>
  );
}
