"use client";

import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useUrlState } from "@/hooks/use-url-state";
import { COUNTRY_LABEL } from "@/lib/ai";

const ANY = "any";

/** Filters kept in the URL: engine, region, persona, web search, prompt. */
export function AiFilters({
  personas,
  prompts,
  regions,
  showPrompt = false,
}: {
  personas: { id: number; name: string }[];
  prompts?: { id: number; text: string }[];
  regions: string[];
  showPrompt?: boolean;
}) {
  const { params, set } = useUrlState();
  const pick = (label: string, key: string, items: { value: string; label: string }[], width = "w-44") => {
    const all = [{ value: ANY, label }, ...items];
    return (
      <Select items={all} value={params.get(key) ?? ANY} onValueChange={(v) => set({ [key]: v === ANY ? null : (v as string) })}>
        <SelectTrigger aria-label={label} className={width}>
          <SelectValue />
        </SelectTrigger>
        <SelectContent alignItemWithTrigger={false} align="start">
          {all.map((i) => (
            <SelectItem key={i.value} value={i.value}>
              {i.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    );
  };
  const active = ["engine", "region", "persona_id", "search", "prompt_id"].some((k) => params.has(k));
  return (
    <div className="flex flex-wrap items-center gap-2">
      {pick("All engines", "engine", [
        { value: "openai", label: "OpenAI" },
        { value: "gemini", label: "Gemini" },
        { value: "perplexity", label: "Perplexity" },
        { value: "anthropic", label: "Claude" },
      ])}
      {pick("All regions", "region", regions.map((r) => ({ value: r, label: COUNTRY_LABEL[r] ?? r })))}
      {pick("All personas", "persona_id", [{ value: "0", label: "No persona" }, ...personas.map((p) => ({ value: String(p.id), label: p.name }))])}
      {pick("Search on or off", "search", [
        { value: "true", label: "Web search on" },
        { value: "false", label: "Web search off" },
      ])}
      {showPrompt && prompts && pick("All prompts", "prompt_id", prompts.map((p) => ({ value: String(p.id), label: p.text.slice(0, 60) })), "w-72")}
      {active && (
        <Button variant="ghost" size="sm" onClick={() => set({ engine: null, region: null, persona_id: null, search: null, prompt_id: null })}>
          Clear filters
        </Button>
      )}
    </div>
  );
}
