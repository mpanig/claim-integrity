import { CircleCheck, CircleX, ExternalLink } from "lucide-react";
import { AddUrl, DeleteUrl } from "@/components/audit/audit-actions";
import { EmptyState, TimeAgo } from "@/components/common";
import { Pill, ScoreBadge } from "@/components/status";
import type { Brand, Sku } from "@/lib/types";

export interface Audit {
  id: number;
  url: string;
  brand_name: string;
  sku_name: string | null;
  latest: null | {
    checked_at: string;
    status: "ok" | "blocked" | "error";
    http_status: number | null;
    note: string | null;
    structured: { found?: boolean; score?: number; present?: string[]; missing?: string[]; issues?: string[] };
    crawlability: { score?: number; bots?: { bot: string; purpose: string; allowed: boolean }[]; issues?: string[] };
    freshness: { newest?: string | null; age_days?: number | null; stale?: boolean; facts?: { ingredients_on_page?: number }; issues?: string[] };
  };
}

export interface Entity {
  brand_id: number;
  brand_name: string;
  latest: null | { checked_at: string; qid: string | null; label: string | null; description: string | null; wikipedia_url: string | null; facts: Record<string, string[]>; missing: string[]; score: number; note: string | null };
}

function Issues({ items, checked = true }: { items?: string[]; checked?: boolean }) {
  if (!checked) return <p className="text-xs text-muted-foreground">Not checked: the page could not be fetched.</p>;
  if (!items?.length)
    return (
      <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
        <CircleCheck className="size-3.5 text-good" /> No issues found
      </p>
    );
  return (
    <ul className="flex list-disc flex-col gap-1 pl-4 text-xs">
      {items.map((i) => (
        <li key={i}>{i}</li>
      ))}
    </ul>
  );
}

type Section = "structured" | "crawl" | "freshness";

/** Audited pages, showing the chosen checks. Adding pages is available wherever the list shows. */
export function PageAuditList({ audits, brands, skus, show }: { audits: Audit[]; brands: Brand[]; skus: Sku[]; show: Section[] }) {
  return (
    <div className="flex flex-col gap-4">
      <AddUrl brands={brands} skus={skus.map((s) => ({ id: s.id, name: s.name, brand_id: s.brand_id }))} />
      {audits.length === 0 && <EmptyState title="No pages yet">Add a brand or retailer product page above.</EmptyState>}
      {audits.map((a) => {
        const r = a.latest;
        return (
          <article key={a.id} className="flex flex-col gap-3 rounded-xl border p-4">
            <div className="flex flex-wrap items-start justify-between gap-2">
              <div className="min-w-0">
                <a href={a.url} target="_blank" rel="noreferrer" className="inline-flex max-w-full items-center gap-1 truncate font-medium hover:underline">
                  {a.url} <ExternalLink className="size-3.5 shrink-0" />
                </a>
                <p className="text-xs text-muted-foreground">
                  {a.brand_name}
                  {a.sku_name && ` · ${a.sku_name}`} ·{" "}
                  {r ? (
                    <>
                      checked <TimeAgo iso={r.checked_at} />
                    </>
                  ) : (
                    "not checked yet"
                  )}
                </p>
              </div>
              <div className="flex items-center gap-2">
                {r && (
                  <Pill tone={r.status === "ok" ? "good" : r.status === "blocked" ? "serious" : "critical"}>
                    {r.status === "ok" ? "Checked" : r.status === "blocked" ? "Blocked" : "Error"}
                  </Pill>
                )}
                <DeleteUrl id={a.id} />
              </div>
            </div>
            {r?.note && <p className="text-sm text-muted-foreground">{r.note}</p>}
            {r && (
              <div className={show.length > 1 ? "grid gap-3 lg:grid-cols-2" : "grid gap-3"}>
                {show.includes("structured") && (
                  <section className="flex flex-col gap-2 rounded-lg bg-muted/40 p-3">
                    <h3 className="flex items-center justify-between text-sm font-medium">
                      Structured product data {r.structured.score !== undefined && <ScoreBadge score={r.structured.score} />}
                    </h3>
                    {r.status === "ok" && r.structured.present && <p className="text-xs text-muted-foreground">Has: {r.structured.present.join(", ") || "nothing"}</p>}
                    <Issues items={r.structured.issues} checked={r.status === "ok"} />
                  </section>
                )}
                {show.includes("crawl") && (
                  <section className="flex flex-col gap-2 rounded-lg bg-muted/40 p-3">
                    <h3 className="flex items-center justify-between text-sm font-medium">
                      AI crawler access {r.crawlability.score !== undefined && <ScoreBadge score={r.crawlability.score} />}
                    </h3>
                    {r.crawlability.bots && (
                      <ul className="grid grid-cols-2 gap-x-2 gap-y-0.5 text-xs sm:grid-cols-3">
                        {r.crawlability.bots.map((b) => (
                          <li key={b.bot} className="flex items-center gap-1" title={b.purpose}>
                            {b.allowed ? <CircleCheck className="size-3.5 text-good" /> : <CircleX className="size-3.5 text-critical" />}
                            {b.bot}
                          </li>
                        ))}
                      </ul>
                    )}
                    <Issues items={r.crawlability.issues} />
                  </section>
                )}
                {show.includes("freshness") && (
                  <section className="flex flex-col gap-2 rounded-lg bg-muted/40 p-3">
                    <h3 className="text-sm font-medium">Freshness</h3>
                    <p className="text-xs text-muted-foreground">
                      {r.freshness.newest ? `Last dated ${r.freshness.age_days} days ago` : r.status === "ok" ? "No date found" : "Not checked"}
                      {r.freshness.facts?.ingredients_on_page !== undefined && ` · ${Math.round(r.freshness.facts.ingredients_on_page * 100)}% of approved ingredients shown`}
                    </p>
                    <Issues items={r.freshness.issues} checked={r.status === "ok"} />
                  </section>
                )}
              </div>
            )}
          </article>
        );
      })}
    </div>
  );
}

/** Wikidata / Wikipedia facts per brand. */
export function EntityClarity({ entities }: { entities: Entity[] }) {
  return (
    <div className="grid gap-3 md:grid-cols-2">
      {entities.map((e) => (
        <div key={e.brand_id} className="flex flex-col gap-2 rounded-xl border p-3">
          <div className="flex items-center justify-between gap-2">
            <span className="font-medium">{e.brand_name}</span>
            {e.latest ? <ScoreBadge score={e.latest.score} /> : <Pill tone="neutral">Not checked</Pill>}
          </div>
          {e.latest && (
            <>
              {e.latest.note && <p className="text-sm text-muted-foreground">{e.latest.note}</p>}
              {e.latest.qid && (
                <p className="text-xs text-muted-foreground">
                  <a className="hover:underline" href={`https://www.wikidata.org/wiki/${e.latest.qid}`} target="_blank" rel="noreferrer">
                    Wikidata {e.latest.qid}
                  </a>
                  {e.latest.description && ` · “${e.latest.description}”`}
                  {e.latest.wikipedia_url && (
                    <>
                      {" · "}
                      <a className="hover:underline" href={e.latest.wikipedia_url} target="_blank" rel="noreferrer">
                        Wikipedia
                      </a>
                    </>
                  )}
                </p>
              )}
              {Object.keys(e.latest.facts).length > 0 && (
                <dl className="grid grid-cols-[9rem_1fr] gap-x-2 text-xs">
                  {Object.entries(e.latest.facts).map(([k, v]) => (
                    <div key={k} className="contents">
                      <dt className="text-muted-foreground">{k}</dt>
                      <dd>{v.join(", ")}</dd>
                    </div>
                  ))}
                </dl>
              )}
              {e.latest.missing.length > 0 && <p className="text-xs">Missing: {e.latest.missing.join(", ")}</p>}
              <p className="text-xs text-muted-foreground">
                Checked <TimeAgo iso={e.latest.checked_at} />
              </p>
            </>
          )}
        </div>
      ))}
    </div>
  );
}
