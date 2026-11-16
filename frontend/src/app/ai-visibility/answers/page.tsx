import type { Metadata } from "next";
import { Suspense } from "react";
import { AiFilters } from "@/components/ai/ai-filters";
import { AnswerLink, ViewToggle } from "@/components/ai/answer-link";
import { AnswerSheet } from "@/components/ai/answer-sheet";
import { AiTabs } from "@/components/ai/ai-tabs";
import { EngineStrip } from "@/components/ai/engine-strip";
import { DemoBadge, EmptyState, LoadingBlock, TimeAgo } from "@/components/common";
import { PageHeader } from "@/components/page-header";
import { Pill } from "@/components/status";
import { aiFilterParams, type AnswerBrief, COUNTRY_LABEL, type EngineMode, type EngineStatus, type Library } from "@/lib/ai";
import { serverGet } from "@/lib/api";
import { first, type SP } from "@/lib/params";

export const metadata: Metadata = { title: "AI answers" };

export default function AnswersPage({ searchParams }: PageProps<"/ai-visibility/answers">) {
  return (
    <>
      <PageHeader title="AI visibility" description="Read the answers themselves, or compare one question across engines and regions." />
      <AiTabs />
      <Suspense fallback={<LoadingBlock rows={3} />}>
        <Answers searchParams={searchParams} />
      </Suspense>
      <Suspense>
        <AnswerSheet />
      </Suspense>
    </>
  );
}

async function Answers({ searchParams }: { searchParams: Promise<SP> }) {
  const sp = await searchParams;
  const view = first(sp.view) === "compare" ? "compare" : "list";
  const lib = await serverGet<Library>("/ai/library");
  const promptId = first(sp.prompt_id) ?? (view === "compare" ? String(lib.prompts[0]?.id ?? "") : undefined);
  const filters = aiFilterParams(sp);
  // Compare like with like: one persona across every cell (no persona unless one is chosen).
  const persona = view === "compare" && !filters.persona_id ? "0" : filters.persona_id;
  const params = { ...filters, persona_id: persona, prompt_id: promptId, limit: view === "compare" ? 500 : 60 };
  const [data, engines] = await Promise.all([
    serverGet<{ total: number; engines: EngineMode[]; items: AnswerBrief[] }>("/ai/answers", params),
    serverGet<EngineStatus[]>("/ai/engines"),
  ]);
  const regions = [...new Set(data.items.map((a) => a.region))].sort();

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <EngineStrip modes={data.engines} statuses={engines} />
        <ViewToggle view={view} />
      </div>
      <AiFilters personas={lib.personas} prompts={lib.prompts} regions={regions.length ? regions : ["US", "IN"]} showPrompt />
      {data.items.length === 0 ? (
        <EmptyState title="No answers match">Change the filters or run a test plan.</EmptyState>
      ) : view === "compare" ? (
        <Compare items={data.items} />
      ) : (
        <>
          <p className="text-sm text-muted-foreground">
            {data.total} answers{data.total > data.items.length ? `, showing the latest ${data.items.length}` : ""}
          </p>
          <ul className="flex flex-col divide-y rounded-xl border">
            {data.items.map((a) => (
              <li key={a.id}>
                <AnswerLink id={a.id} className="flex w-full flex-col gap-1 p-3 hover:bg-muted/40">
                  <span className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                    <span className="font-medium text-foreground">{a.engine}</span>
                    {a.model_requested} · {COUNTRY_LABEL[a.region] ?? a.region} · {a.language} · {a.persona ?? "no persona"} · search {a.search_enabled ? "on" : "off"} ·{" "}
                    <TimeAgo iso={a.asked_at} />
                    {a.is_demo && <DemoBadge />}
                    {a.wrong_claims > 0 && <Pill tone="critical">{a.wrong_claims} wrong fact{a.wrong_claims > 1 ? "s" : ""}</Pill>}
                  </span>
                  <span className="line-clamp-2 text-sm">{plain(a.excerpt)}</span>
                  {a.mentions.length > 0 && <span className="text-xs text-muted-foreground">Mentions {a.mentions.join(", ")}</span>}
                </AnswerLink>
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}

/** Markdown emphasis markers out, for short previews. */
function plain(text: string): string {
  return text.replace(/\*\*|__/g, "").replace(/^#+\s*/gm, "");
}

function Compare({ items }: { items: AnswerBrief[] }) {
  // First sample per engine x region for the chosen prompt (and persona filter, if any).
  const engines = [...new Set(items.map((a) => a.engine))].sort();
  const regions = [...new Set(items.map((a) => `${a.region}|${a.language}`))].sort();
  const pick = (engine: string, key: string) =>
    items.filter((a) => a.engine === engine && `${a.region}|${a.language}` === key).sort((x, y) => x.sample_index - y.sample_index)[0];
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[800px] border-separate border-spacing-2 text-sm">
        <thead>
          <tr>
            <th className="w-32 text-left text-xs font-medium text-muted-foreground">Region · language</th>
            {engines.map((e) => (
              <th key={e} className="text-left text-xs font-medium text-muted-foreground">
                {e}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {regions.map((key) => {
            const [region, lang] = key.split("|");
            return (
              <tr key={key}>
                <th scope="row" className="text-left align-top font-medium">
                  {COUNTRY_LABEL[region] ?? region} · {lang}
                </th>
                {engines.map((e) => {
                  const a = pick(e, key);
                  return (
                    <td key={e} className="align-top">
                      {a ? (
                        <AnswerLink id={a.id} className="flex h-full w-full flex-col gap-1 rounded-lg border p-2 hover:bg-muted/40">
                          <span className="flex flex-wrap items-center gap-1 text-xs text-muted-foreground">
                            {a.persona ?? "no persona"}
                            {a.is_demo && <DemoBadge />}
                          </span>
                          <span className="line-clamp-6 text-xs">{plain(a.excerpt)}</span>
                          <span className="text-xs text-muted-foreground">{a.mentions.join(", ") || "no tracked brands"}</span>
                        </AnswerLink>
                      ) : (
                        <span className="text-xs text-muted-foreground">–</span>
                      )}
                    </td>
                  );
                })}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
