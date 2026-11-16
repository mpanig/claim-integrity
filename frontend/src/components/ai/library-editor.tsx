"use client";

import { Plus, Trash2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { INTENT_LABEL, type Library } from "@/lib/ai";
import { api } from "@/lib/api";

function Pick({ items, value, onChange, label, width = "w-44" }: { items: { value: string; label: string }[]; value: string; onChange: (v: string) => void; label: string; width?: string }) {
  return (
    <Select items={items} value={value} onValueChange={(v) => onChange(v as string)}>
      <SelectTrigger className={width} aria-label={label}>
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {items.map((i) => (
          <SelectItem key={i.value} value={i.value}>
            {i.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

export function LibraryEditor({ lib }: { lib: Library }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [prompt, setPrompt] = useState({ text: "", intent: "category", funnel_stage: "awareness", sku_id: "none" });
  const [variant, setVariant] = useState<Record<number, { text: string; language: string }>>({});
  const [persona, setPersona] = useState({ name: "", context: "" });
  const [competitor, setCompetitor] = useState({ name: "", aliases: "" });
  const [aliases, setAliases] = useState<Record<string, string>>({});

  async function call(fn: () => Promise<unknown>, ok: string) {
    setBusy(true);
    try {
      await fn();
      toast.success(ok);
      router.refresh();
      return true;
    } catch (e) {
      toast.error("That didn't work", { description: (e as Error).message });
      return false;
    } finally {
      setBusy(false);
    }
  }

  const languages = Object.entries(lib.languages).map(([value, label]) => ({ value, label }));
  const skuItems = [{ value: "none", label: "No specific product" }, ...lib.skus.map((s) => ({ value: String(s.id), label: s.name }))];

  return (
    <div className="flex flex-col gap-4">
      <Card>
        <CardHeader>
          <CardTitle>Prompts</CardTitle>
          <CardDescription>
            Placeholders: {"{brand} {product} {category} {competitor} {city} {country}"}. Add wording variants (in any language) to test how phrasing changes answers.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          {lib.prompts.map((p) => (
            <div key={p.id} className="flex flex-col gap-2 rounded-xl border p-3">
              <div className="flex items-start justify-between gap-2">
                <div>
                  <p className="font-medium">{p.text}</p>
                  <p className="text-xs text-muted-foreground">
                    {INTENT_LABEL[p.intent] ?? p.intent} · {p.funnel_stage}
                    {p.sku_name && ` · ${p.sku_name}`}
                    {p.competitor && ` · vs ${p.competitor}`}
                  </p>
                </div>
                <Button variant="ghost" size="icon-sm" aria-label="Delete prompt" disabled={busy} onClick={() => call(() => api(`/ai/prompts/${p.id}`, { method: "DELETE" }), "Prompt deleted")}>
                  <Trash2 />
                </Button>
              </div>
              <ul className="flex flex-col gap-1 pl-3 text-sm">
                {p.variants.map((v) => (
                  <li key={v.id} className="flex items-center gap-2">
                    <span className="w-8 text-xs text-muted-foreground uppercase">{v.language}</span>
                    <span className="flex-1">{v.text}</span>
                    <Button variant="ghost" size="icon-xs" aria-label="Delete variant" disabled={busy} onClick={() => call(() => api(`/ai/variants/${v.id}`, { method: "DELETE" }), "Variant deleted")}>
                      <Trash2 />
                    </Button>
                  </li>
                ))}
              </ul>
              <div className="flex flex-wrap gap-2 pl-3">
                <Input
                  className="min-w-64 flex-1"
                  placeholder="Add a wording variant"
                  aria-label="New wording variant"
                  value={variant[p.id]?.text ?? ""}
                  onChange={(e) => setVariant({ ...variant, [p.id]: { language: variant[p.id]?.language ?? "en", text: e.target.value } })}
                />
                <Pick items={languages} label="Language" width="w-32" value={variant[p.id]?.language ?? "en"} onChange={(l) => setVariant({ ...variant, [p.id]: { text: variant[p.id]?.text ?? "", language: l } })} />
                <Button
                  variant="outline"
                  size="sm"
                  disabled={busy || (variant[p.id]?.text ?? "").trim().length < 3}
                  onClick={async () => {
                    if (await call(() => api(`/ai/prompts/${p.id}/variants`, { method: "POST", body: variant[p.id] }), "Variant added")) setVariant({ ...variant, [p.id]: { text: "", language: "en" } });
                  }}
                >
                  <Plus /> Add
                </Button>
              </div>
            </div>
          ))}
          <div className="flex flex-wrap items-end gap-2 border-t pt-3">
            <Input className="min-w-72 flex-1" placeholder="New prompt, e.g. Is {product} safe for babies?" aria-label="New prompt" value={prompt.text} onChange={(e) => setPrompt({ ...prompt, text: e.target.value })} />
            <Pick items={lib.intents.map((i) => ({ value: i, label: INTENT_LABEL[i] ?? i }))} label="Intent" value={prompt.intent} onChange={(v) => setPrompt({ ...prompt, intent: v })} />
            <Pick items={lib.funnel_stages.map((s) => ({ value: s, label: s }))} label="Funnel stage" width="w-36" value={prompt.funnel_stage} onChange={(v) => setPrompt({ ...prompt, funnel_stage: v })} />
            <Pick items={skuItems} label="Product" width="w-56" value={prompt.sku_id} onChange={(v) => setPrompt({ ...prompt, sku_id: v })} />
            <Button
              disabled={busy || prompt.text.trim().length < 5}
              onClick={async () => {
                const body = { ...prompt, sku_id: prompt.sku_id === "none" ? null : Number(prompt.sku_id) };
                if (await call(() => api("/ai/prompts", { method: "POST", body }), "Prompt added")) setPrompt({ ...prompt, text: "" });
              }}
            >
              <Plus /> Add prompt
            </Button>
          </div>
        </CardContent>
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Personas</CardTitle>
            <CardDescription>Context added before the question, written as the shopper would say it.</CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-2">
            {lib.personas.map((p) => (
              <div key={p.id} className="flex items-start gap-2 text-sm">
                <div className="flex-1">
                  <p className="font-medium">{p.name}</p>
                  <p className="text-muted-foreground">{p.context}</p>
                </div>
                <Button variant="ghost" size="icon-sm" aria-label={`Delete ${p.name}`} disabled={busy} onClick={() => call(() => api(`/ai/personas/${p.id}`, { method: "DELETE" }), "Persona deleted")}>
                  <Trash2 />
                </Button>
              </div>
            ))}
            <div className="flex flex-col gap-2 border-t pt-3">
              <Input placeholder="Name, e.g. Teen with acne" aria-label="Persona name" value={persona.name} onChange={(e) => setPersona({ ...persona, name: e.target.value })} />
              <Input placeholder="Context, e.g. I'm 16 and my skin is oily and breaks out." aria-label="Persona context" value={persona.context} onChange={(e) => setPersona({ ...persona, context: e.target.value })} />
              <Button
                variant="outline"
                size="sm"
                className="w-fit"
                disabled={busy || !persona.name.trim() || persona.context.trim().length < 5}
                onClick={async () => {
                  if (await call(() => api("/ai/personas", { method: "POST", body: persona }), "Persona added")) setPersona({ name: "", context: "" });
                }}
              >
                <Plus /> Add persona
              </Button>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Competitors and aliases</CardTitle>
            <CardDescription>Names to recognise in answers. Aliases catch other spellings and short names.</CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-3">
            {[...lib.brands.map((b) => ({ key: `b${b.id}`, label: `${b.name} (ours)`, aliases: b.aliases, body: { brand_id: b.id } })), ...lib.skus.map((s) => ({ key: `s${s.id}`, label: s.name, aliases: s.aliases, body: { sku_id: s.id } }))].map((row) => (
              <div key={row.key} className="flex flex-wrap items-center gap-2 text-sm">
                <span className="w-56 font-medium">{row.label}</span>
                <Input
                  className="min-w-48 flex-1"
                  aria-label={`Aliases for ${row.label}`}
                  value={aliases[row.key] ?? row.aliases.join(", ")}
                  onChange={(e) => setAliases({ ...aliases, [row.key]: e.target.value })}
                />
                {aliases[row.key] !== undefined && (
                  <Button size="sm" variant="outline" disabled={busy} onClick={() => call(() => api("/ai/aliases", { method: "PUT", body: { ...row.body, aliases: aliases[row.key].split(",") } }), "Aliases saved")}>
                    Save
                  </Button>
                )}
              </div>
            ))}
            <div className="border-t pt-3">
              <ul className="flex flex-col gap-1 text-sm">
                {lib.competitors.map((c) => (
                  <li key={c.id} className="flex items-center gap-2">
                    <span className="w-40 font-medium">{c.name}</span>
                    <span className="flex-1 text-muted-foreground">{c.aliases.join(", ")}</span>
                    <Button variant="ghost" size="icon-xs" aria-label={`Delete ${c.name}`} disabled={busy} onClick={() => call(() => api(`/ai/competitors/${c.id}`, { method: "DELETE" }), "Competitor removed")}>
                      <Trash2 />
                    </Button>
                  </li>
                ))}
              </ul>
              <div className="mt-2 flex flex-wrap gap-2">
                <Input className="w-40" placeholder="Competitor" aria-label="Competitor name" value={competitor.name} onChange={(e) => setCompetitor({ ...competitor, name: e.target.value })} />
                <Input className="min-w-40 flex-1" placeholder="Aliases, comma separated" aria-label="Competitor aliases" value={competitor.aliases} onChange={(e) => setCompetitor({ ...competitor, aliases: e.target.value })} />
                <Button
                  variant="outline"
                  size="sm"
                  disabled={busy || !competitor.name.trim()}
                  onClick={async () => {
                    if (await call(() => api("/ai/competitors", { method: "POST", body: { name: competitor.name, aliases: competitor.aliases.split(",") } }), "Competitor added")) setCompetitor({ name: "", aliases: "" });
                  }}
                >
                  <Plus /> Add
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
