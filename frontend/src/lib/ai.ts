export type EngineName = "openai" | "gemini" | "perplexity" | "anthropic";

export interface EngineStatus {
  engine: EngineName;
  label: string;
  env_key: string;
  status: "live" | "key missing";
  default_models: string[];
  search: "toggle" | "always";
  location: string;
}

export interface Rate {
  k: number;
  n: number;
  rate: number | null;
  low: number;
  high: number;
}

export interface EngineMode {
  engine: EngineName;
  label: string;
  /** awaiting = key found, no real answers yet (demo hidden). */
  mode: "live" | "demo" | "none" | "awaiting";
  answers: number;
  key?: boolean;
}

export interface Insights {
  answers: number;
  engines: EngineMode[];
  demo: boolean;
  brands: {
    name: string;
    is_own: boolean;
    mention: Rate;
    recommended: Rate;
    share_of_voice: number;
    avg_position: number | null;
    top3: Rate;
    sentiment: number | null;
  }[];
  heatmap: { engine: EngineName; region: string; persona: string; brand: string; mention: Rate; recommended: Rate }[];
  rank: { brand: string; positions: Record<"1" | "2" | "3" | "4" | "5+" | "unranked", number> }[];
  accuracy: {
    sku_id: number;
    sku_name: string;
    claims: number;
    correct: number;
    accuracy: Rate;
    by_verdict: Record<string, number>;
    echoes: { conflict_id: number; label: string; answers: number }[];
  }[];
  wrong_claims: {
    answer_id: number;
    engine: EngineName;
    region: string;
    sku_name: string;
    field: string;
    value: unknown;
    verdict: string;
    quote: string;
    echoes: number[];
    is_demo: boolean;
  }[];
  citations: {
    total: number;
    domains: { domain: string; page_type: string; count: number; share: number }[];
    pages: { url: string; title: string | null; count: number }[];
    by_type: Record<string, number>;
  };
  trend: ({ week: string; answers: number } & Record<string, number | string | null>)[];
}

export interface AnswerBrief {
  id: number;
  prompt_id: number;
  engine: EngineName;
  model_requested: string;
  model_version: string | null;
  search_enabled: boolean;
  region: string;
  city: string | null;
  language: string;
  location_mode: string;
  persona: string | null;
  sample_index: number;
  asked_at: string;
  is_demo: boolean;
  analyser: string | null;
  excerpt: string;
  mentions: string[];
  wrong_claims: number;
  citations: number;
}

export interface AnswerDetail extends AnswerBrief {
  prompt_text: string;
  prompt: string;
  answer: string;
  latency_ms: number | null;
  input_tokens: number | null;
  output_tokens: number | null;
  cost_usd: number | null;
  temperature: number | null;
  mentions_detail: { name: string; is_own: boolean; position: number | null; recommended: boolean; sentiment: number; quote: string }[];
  claims: { sku_name: string; field: string; value: unknown; quote: string; verdict: string | null; severity: number | null; echo_conflict_ids: number[] }[];
  citations_detail: { url: string; domain: string; title: string | null; page_type: string }[];
}

export interface Library {
  intents: string[];
  funnel_stages: string[];
  languages: Record<string, string>;
  prompts: {
    id: number;
    text: string;
    intent: string;
    funnel_stage: string;
    category: string | null;
    competitor: string | null;
    sku_id: number | null;
    sku_name: string | null;
    variants: { id: number; language: string; text: string }[];
  }[];
  personas: { id: number; name: string; context: string }[];
  competitors: { id: number; name: string; aliases: string[] }[];
  brands: { id: number; name: string; aliases: string[] }[];
  skus: { id: number; name: string; aliases: string[] }[];
}

export interface PlanConfig {
  prompt_ids: number[];
  engines: { engine: EngineName; models: string[] }[];
  search_modes: boolean[];
  regions: { country: string; city: string | null; languages: string[] }[];
  persona_ids: (number | null)[];
  variants: "all" | "first";
  samples: number;
}

export interface Estimate {
  cells: number;
  runnable_calls: number;
  est_usd: number;
  est_usd_all_engines: number;
  engines: { engine: EngineName; label: string; status: string; calls: number; est_usd: number }[];
  note: string;
}

export interface AiRunRow {
  id: number;
  status: string;
  started_at: string;
  finished_at: string | null;
  planned_calls: number;
  done_calls: number;
  skipped: { engine: string; reason: string; calls: number }[];
  errors: { engine?: string; error: string }[];
  budget_usd: number;
  est_cost_usd: number;
  cost_usd: number;
  analyser: string | null;
  is_demo: boolean;
}

export const INTENT_LABEL: Record<string, string> = {
  category: "Best-of (category)",
  problem: "Problem-led",
  attribute: "Product question",
  versus: "Brand vs brand",
  where_to_buy: "Where to buy",
};

export const COUNTRY_LABEL: Record<string, string> = { US: "United States", IN: "India", GB: "United Kingdom", CA: "Canada", AU: "Australia", DE: "Germany", FR: "France" };

/** URL filters -> /ai/insights and /ai/answers query params. */
export function aiFilterParams(sp: Record<string, string | string[] | undefined>) {
  const one = (v: string | string[] | undefined) => (Array.isArray(v) ? v[0] : v);
  const many = (v: string | string[] | undefined) => (v === undefined ? [] : Array.isArray(v) ? v : [v]);
  return {
    engine: many(sp.engine),
    region: many(sp.region),
    persona_id: one(sp.persona_id),
    prompt_id: one(sp.prompt_id),
    search: one(sp.search),
  };
}

export function pct(r: number | null | undefined): string {
  return r === null || r === undefined ? "–" : `${Math.round(r * 100)}%`;
}

export function rateRange(r: Rate): string {
  return r.n ? `${pct(r.rate)} (${pct(r.low)}–${pct(r.high)})` : "–";
}
