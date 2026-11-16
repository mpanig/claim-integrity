"use client";

import { ExternalLink, Repeat } from "lucide-react";
import { useEffect, useState } from "react";
import { ConflictLink, DemoBadge, TimeAgo } from "@/components/common";
import { Pill, VerdictBadge } from "@/components/status";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { useUrlState } from "@/hooks/use-url-state";
import { type AnswerDetail, COUNTRY_LABEL } from "@/lib/ai";
import { api } from "@/lib/api";
import { displayValue } from "@/lib/format";
import type { Verdict } from "@/lib/types";

export function AnswerSheet() {
  const { params, set } = useUrlState();
  const id = params.get("answer");
  return (
    <Sheet open={!!id} onOpenChange={(o) => !o && set({ answer: null })}>
      <SheetContent side="right" className="w-full gap-0 overflow-y-auto p-0 data-[side=right]:sm:max-w-2xl">
        {id && <AnswerPanel key={id} id={id} />}
      </SheetContent>
    </Sheet>
  );
}

function AnswerPanel({ id }: { id: string }) {
  const [a, setA] = useState<AnswerDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let cancelled = false;
    api<AnswerDetail>(`/ai/answers/${id}`)
      .then((d) => !cancelled && setA(d))
      .catch((e: Error) => !cancelled && setError(e.message));
    return () => {
      cancelled = true;
    };
  }, [id]);
  if (error) return <p className="p-6 text-sm text-muted-foreground">{error}</p>;
  if (!a)
    return (
      <div className="flex flex-col gap-3 p-6" aria-busy="true">
        <SheetTitle className="sr-only">Loading answer</SheetTitle>
        <Skeleton className="h-6 w-1/2" />
        <Skeleton className="h-40 w-full" />
      </div>
    );
  const facts: [string, string][] = [
    ["Engine and model", `${a.engine} · asked for ${a.model_requested}${a.model_version ? `, answered by ${a.model_version}` : ""}`],
    ["Web search", a.search_enabled ? "on" : "off"],
    ["Region", `${a.city ? `${a.city}, ` : ""}${COUNTRY_LABEL[a.region] ?? a.region} (${a.location_mode === "api" ? "sent through the API" : a.location_mode === "prompt-only" ? "stated in the question" : "none"})`],
    ["Language", a.language],
    ["Persona", a.persona ?? "none"],
    ["Sample", `#${a.sample_index}`],
    ["Temperature", a.temperature ?? "provider default"].map(String) as [string, string],
    ["Tokens", a.input_tokens != null ? `${a.input_tokens} in, ${a.output_tokens} out` : "–"],
    ["Latency", a.latency_ms != null ? `${(a.latency_ms / 1000).toFixed(1)} s` : "–"],
    ["Cost", a.cost_usd != null ? `$${a.cost_usd.toFixed(4)}` : "–"],
    ["Analysed by", a.analyser ?? "–"],
  ];
  return (
    <>
      <SheetHeader className="gap-2 border-b p-6 pr-12">
        <div className="flex flex-wrap items-center gap-2">
          {a.is_demo && <DemoBadge />}
          <span className="text-xs text-muted-foreground">
            <TimeAgo iso={a.asked_at} />
          </span>
        </div>
        <SheetTitle className="text-lg leading-snug">{a.prompt}</SheetTitle>
        <SheetDescription>Exactly what was sent: “{a.prompt_text}”</SheetDescription>
      </SheetHeader>
      <div className="flex flex-col gap-6 p-6">
        <section>
          <h3 className="mb-2 text-sm font-medium">Answer</h3>
          <div className="rounded-xl bg-muted/60 p-4 text-sm leading-relaxed whitespace-pre-wrap">{a.answer.replace(/\*\*/g, "")}</div>
        </section>
        <section>
          <h3 className="mb-2 text-sm font-medium">Brands mentioned</h3>
          {a.mentions_detail.length === 0 ? (
            <p className="text-sm text-muted-foreground">None of the tracked brands.</p>
          ) : (
            <ul className="flex flex-col gap-1.5 text-sm">
              {a.mentions_detail.map((m) => (
                <li key={m.name} className="flex flex-wrap items-center gap-2">
                  <span className="font-medium">{m.name}</span>
                  {m.is_own && <Pill tone="good">Ours</Pill>}
                  <span className="text-muted-foreground">
                    {m.position ? `#${m.position}` : "not ranked"} · {m.recommended ? "recommended" : "not recommended"} · sentiment {m.sentiment > 0 ? "+" : ""}
                    {m.sentiment}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </section>
        <section>
          <h3 className="mb-2 text-sm font-medium">Product facts stated</h3>
          {a.claims.length === 0 ? (
            <p className="text-sm text-muted-foreground">No product facts.</p>
          ) : (
            <ul className="flex flex-col gap-2">
              {a.claims.map((c, i) => (
                <li key={i} className="flex flex-col gap-1 rounded-lg border p-2 text-sm">
                  <span className="flex flex-wrap items-center gap-2">
                    {c.verdict ? (
                      <VerdictBadge verdict={c.verdict as Verdict} label={c.verdict === "outdated" ? "Outdated ingredient info" : undefined} />
                    ) : (
                      <Pill tone="good">Matches the truth sheet</Pill>
                    )}
                    <span className="font-medium">{displayValue(c.value)}</span>
                    <span className="text-xs text-muted-foreground">{c.sku_name}</span>
                  </span>
                  <span className="text-xs text-muted-foreground">“{c.quote}”</span>
                  {c.echo_conflict_ids.map((cid) => (
                    <ConflictLink key={cid} id={cid} className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground">
                      <Repeat className="size-3.5" /> Repeats an open page issue
                    </ConflictLink>
                  ))}
                </li>
              ))}
            </ul>
          )}
        </section>
        <section>
          <h3 className="mb-2 text-sm font-medium">Sources cited</h3>
          {a.citations_detail.length === 0 ? (
            <p className="text-sm text-muted-foreground">No sources cited.</p>
          ) : (
            <ul className="flex flex-col gap-1 text-sm">
              {a.citations_detail.map((c) => (
                <li key={c.url} className="flex items-center gap-2">
                  <span className="w-20 shrink-0 text-xs text-muted-foreground">{c.page_type}</span>
                  <a href={c.url} target="_blank" rel="noreferrer" className="inline-flex min-w-0 items-center gap-1 truncate hover:underline">
                    {c.title || c.domain} <ExternalLink className="size-3 shrink-0" />
                  </a>
                </li>
              ))}
            </ul>
          )}
        </section>
        <section>
          <h3 className="mb-2 text-sm font-medium">How it was asked</h3>
          <dl className="grid grid-cols-[9rem_1fr] gap-x-3 gap-y-1 text-sm">
            {facts.map(([k, v]) => (
              <div key={k} className="contents">
                <dt className="text-muted-foreground">{k}</dt>
                <dd>{v}</dd>
              </div>
            ))}
          </dl>
        </section>
      </div>
    </>
  );
}
