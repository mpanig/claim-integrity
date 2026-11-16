"use client";

import { Calculator, Play, Plus, Save, Trash2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";
import { Pill } from "@/components/status";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { COUNTRY_LABEL, type EngineName, type EngineStatus, type Estimate, INTENT_LABEL, type Library, type PlanConfig } from "@/lib/ai";
import { api } from "@/lib/api";

interface Saved {
  id: number;
  name: string;
  config: PlanConfig;
  budget_usd: number;
  schedule: string;
}

function Check({ checked, onChange, label, hint }: { checked: boolean; onChange: (v: boolean) => void; label: React.ReactNode; hint?: string }) {
  return (
    <label className="flex cursor-pointer items-start gap-2 text-sm">
      <Checkbox checked={checked} onCheckedChange={(v) => onChange(!!v)} className="mt-0.5" />
      <span>
        {label}
        {hint && <span className="block text-xs text-muted-foreground">{hint}</span>}
      </span>
    </label>
  );
}

export function PlanBuilder({ lib, engines, saved }: { lib: Library; engines: EngineStatus[]; saved: Saved[] }) {
  const router = useRouter();
  const initial = saved[0]?.config;
  const [prompts, setPrompts] = useState<number[]>(initial?.prompt_ids ?? lib.prompts.map((p) => p.id));
  const [engineModels, setEngineModels] = useState<Record<string, string | null>>(
    Object.fromEntries(
      engines.map((e) => {
        const chosen = initial?.engines.find((x) => x.engine === e.engine);
        return [e.engine, chosen ? chosen.models.join(", ") : null];
      }),
    ),
  );
  const [search, setSearch] = useState<boolean[]>(initial?.search_modes ?? [true]);
  const [regions, setRegions] = useState(initial?.regions ?? [{ country: "US", city: "New York", languages: ["en"] }]);
  const [personas, setPersonas] = useState<(number | null)[]>(initial?.persona_ids ?? [null]);
  const [samples, setSamples] = useState(initial?.samples ?? 3);
  const [variants, setVariants] = useState<"all" | "first">(initial?.variants ?? "first");
  const [budget, setBudget] = useState(saved[0]?.budget_usd ?? 5);
  const [name, setName] = useState("");
  const [schedule, setSchedule] = useState("none");
  const [est, setEst] = useState<Estimate | null>(null);
  const [busy, setBusy] = useState(false);

  const config = (): PlanConfig => ({
    prompt_ids: prompts,
    engines: Object.entries(engineModels)
      .filter(([, m]) => m !== null)
      .map(([engine, models]) => ({ engine: engine as EngineName, models: (models ?? "").split(",").map((s) => s.trim()).filter(Boolean) })),
    search_modes: search,
    regions,
    persona_ids: personas,
    variants,
    samples,
  });

  async function call<T>(fn: () => Promise<T>, ok?: (r: T) => string): Promise<T | null> {
    setBusy(true);
    try {
      const r = await fn();
      if (ok) toast.success(ok(r));
      return r;
    } catch (e) {
      toast.error("That didn't work", { description: (e as Error).message });
      return null;
    } finally {
      setBusy(false);
    }
  }

  const toggle = <T,>(list: T[], v: T, on: boolean) => (on ? [...new Set([...list, v])] : list.filter((x) => x !== v));
  const languageItems = Object.entries(lib.languages).map(([value, label]) => ({ value, label }));
  const countryItems = Object.entries(COUNTRY_LABEL).map(([value, label]) => ({ value, label }));
  const scheduleItems = [
    { value: "none", label: "Run only when I click" },
    { value: "daily", label: "Every day" },
    { value: "weekly", label: "Every week" },
  ];
  const savedItems = saved.map((s) => ({ value: String(s.id), label: s.name }));

  return (
    <div className="flex flex-col gap-4">
      {saved.length > 0 && (
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <span className="text-muted-foreground">Start from a saved plan:</span>
          <Select
            items={savedItems}
            onValueChange={(v) => {
              const s = saved.find((x) => String(x.id) === v);
              if (!s) return;
              const c = s.config;
              setPrompts(c.prompt_ids);
              setEngineModels(Object.fromEntries(engines.map((e) => [e.engine, c.engines.find((x) => x.engine === e.engine)?.models.join(", ") ?? null])));
              setSearch(c.search_modes);
              setRegions(c.regions);
              setPersonas(c.persona_ids);
              setSamples(c.samples);
              setVariants(c.variants);
              setBudget(s.budget_usd);
              setEst(null);
            }}
          >
            <SelectTrigger className="w-64" aria-label="Saved plan">
              <SelectValue placeholder="Choose a plan" />
            </SelectTrigger>
            <SelectContent>
              {savedItems.map((s) => (
                <SelectItem key={s.value} value={s.value}>
                  {s.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>1. Questions</CardTitle>
            <CardDescription>Each question is asked in its wording variants (one or all).</CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-2">
            {lib.prompts.map((p) => (
              <Check
                key={p.id}
                checked={prompts.includes(p.id)}
                onChange={(on) => setPrompts(toggle(prompts, p.id, on))}
                label={p.text}
                hint={`${INTENT_LABEL[p.intent] ?? p.intent} · ${p.funnel_stage}${p.sku_name ? ` · ${p.sku_name}` : ""} · ${p.variants.length} variant${p.variants.length === 1 ? "" : "s"}`}
              />
            ))}
            <div className="mt-2 flex gap-4">
              <Check checked={variants === "first"} onChange={(on) => setVariants(on ? "first" : "all")} label="Main wording only" hint="Untick to ask every wording variant too" />
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>2. Engines and models</CardTitle>
            <CardDescription>Engines without a key are skipped and cost nothing. Several models: separate with commas.</CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-3">
            {engines.map((e) => (
              <div key={e.engine} className="flex flex-col gap-1.5">
                <div className="flex items-center justify-between gap-2">
                  <Check
                    checked={engineModels[e.engine] !== null}
                    onChange={(on) => setEngineModels({ ...engineModels, [e.engine]: on ? e.default_models.join(", ") : null })}
                    label={e.label}
                    hint={`Web search: ${e.search === "always" ? "always on" : "on or off"} · Region: ${e.location}`}
                  />
                  <Pill tone={e.status === "live" ? "good" : "neutral"}>{e.status === "live" ? "Key set" : `${e.env_key} missing`}</Pill>
                </div>
                {engineModels[e.engine] !== null && (
                  <Input
                    aria-label={`${e.label} models`}
                    value={engineModels[e.engine] ?? ""}
                    onChange={(ev) => setEngineModels({ ...engineModels, [e.engine]: ev.target.value })}
                  />
                )}
              </div>
            ))}
            <div className="flex gap-4 border-t pt-3">
              <Check checked={search.includes(true)} onChange={(on) => setSearch(toggle(search, true, on))} label="Web search on" />
              <Check checked={search.includes(false)} onChange={(on) => setSearch(toggle(search, false, on))} label="Web search off" hint="Model knowledge only" />
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>3. Regions and languages</CardTitle>
            <CardDescription>Region goes through the API where it supports a user location (with web search), otherwise into the question.</CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-3">
            {regions.map((r, i) => (
              <div key={i} className="flex flex-wrap items-end gap-2 rounded-lg border p-2">
                <Select items={countryItems} value={r.country} onValueChange={(v) => setRegions(regions.map((x, j) => (j === i ? { ...x, country: v as string } : x)))}>
                  <SelectTrigger className="w-44" aria-label="Country">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {countryItems.map((c) => (
                      <SelectItem key={c.value} value={c.value}>
                        {c.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <Input
                  className="w-36"
                  aria-label="City"
                  placeholder="City (optional)"
                  value={r.city ?? ""}
                  onChange={(e) => setRegions(regions.map((x, j) => (j === i ? { ...x, city: e.target.value || null } : x)))}
                />
                <div className="flex flex-wrap gap-3">
                  {languageItems.map((l) => (
                    <Check
                      key={l.value}
                      checked={r.languages.includes(l.value)}
                      onChange={(on) => setRegions(regions.map((x, j) => (j === i ? { ...x, languages: toggle(x.languages, l.value, on) } : x)))}
                      label={l.label}
                    />
                  ))}
                </div>
                <Button variant="ghost" size="icon-sm" aria-label="Remove region" onClick={() => setRegions(regions.filter((_, j) => j !== i))}>
                  <Trash2 />
                </Button>
              </div>
            ))}
            <Button variant="outline" size="sm" className="w-fit" onClick={() => setRegions([...regions, { country: "IN", city: null, languages: ["en"] }])}>
              <Plus /> Add region
            </Button>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>4. Personas and repeats</CardTitle>
            <CardDescription>Answers vary run to run, so each combination is asked several times and reported as a rate.</CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-3">
            <Check checked={personas.includes(null)} onChange={(on) => setPersonas(toggle(personas, null, on))} label="No persona" hint="The plain question" />
            {lib.personas.map((p) => (
              <Check key={p.id} checked={personas.includes(p.id)} onChange={(on) => setPersonas(toggle(personas, p.id, on))} label={p.name} hint={p.context} />
            ))}
            <div className="grid grid-cols-2 gap-3 border-t pt-3">
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="samples">Samples per combination</Label>
                <Input id="samples" type="number" min={1} max={10} value={samples} onChange={(e) => setSamples(Math.max(1, Math.min(10, Number(e.target.value) || 1)))} />
              </div>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="budget">Budget cap (USD)</Label>
                <Input id="budget" type="number" min={0.5} step={0.5} value={budget} onChange={(e) => setBudget(Number(e.target.value) || 1)} />
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>5. Estimate and run</CardTitle>
          <CardDescription>Check the number of calls and the cost before anything is spent. The run stops at the budget cap.</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" disabled={busy} onClick={async () => setEst(await call(() => api<Estimate>("/ai/estimate", { method: "POST", body: { config: config(), budget_usd: budget } })))}>
              <Calculator /> Estimate
            </Button>
            <Button
              disabled={busy || !est || est.runnable_calls === 0}
              onClick={async () => {
                const r = await call(() => api<{ id: number }>("/ai/runs", { method: "POST", body: { config: config(), budget_usd: budget } }), (r) => `Run ${r.id} started`);
                if (r) router.refresh();
              }}
            >
              <Play /> Run now
            </Button>
          </div>
          {est && (
            <div className="flex flex-col gap-2 text-sm">
              <p>
                <span className="font-medium">{est.cells} answers</span> in this plan;{" "}
                <span className="font-medium">{est.runnable_calls}</span> can run now (engines with a key), about{" "}
                <span className="font-medium">${est.est_usd.toFixed(2)}</span>. With every engine connected: about ${est.est_usd_all_engines.toFixed(2)}.
              </p>
              <ul className="flex flex-col gap-1">
                {est.engines.map((e) => (
                  <li key={e.engine} className="flex flex-wrap items-center gap-2">
                    <span className="w-24 font-medium">{e.label}</span>
                    <span className="tabular-nums">{e.calls} calls · ~${e.est_usd.toFixed(2)}</span>
                    <Pill tone={e.status === "live" ? "good" : "neutral"}>{e.status === "live" ? "will run" : "skipped: key missing"}</Pill>
                  </li>
                ))}
              </ul>
              <p className="text-xs text-muted-foreground">{est.note}</p>
              {est.runnable_calls === 0 && (
                <p className="text-sm text-muted-foreground">
                  No engine in this plan has an API key yet. Add OPENAI_API_KEY, GEMINI_API_KEY, PERPLEXITY_API_KEY or ANTHROPIC_API_KEY to backend/.env and restart the API.
                </p>
              )}
            </div>
          )}
          <div className="flex flex-wrap items-end gap-2 border-t pt-3">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="plan-name">Save as</Label>
              <Input id="plan-name" className="w-64" placeholder="e.g. Weekly US + India" value={name} onChange={(e) => setName(e.target.value)} />
            </div>
            <Select items={scheduleItems} value={schedule} onValueChange={(v) => setSchedule(v as string)}>
              <SelectTrigger className="w-48" aria-label="Schedule">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {scheduleItems.map((s) => (
                  <SelectItem key={s.value} value={s.value}>
                    {s.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Button
              variant="outline"
              disabled={busy || !name.trim()}
              onClick={async () => {
                if (await call(() => api("/ai/configs", { method: "POST", body: { name, config: config(), budget_usd: budget, schedule } }), () => "Plan saved")) {
                  setName("");
                  router.refresh();
                }
              }}
            >
              <Save /> Save plan
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
