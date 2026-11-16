"use client";

import { CircleCheck, CircleX, Copy, Download, ExternalLink, FileText, Gauge } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";
import { DemoBadge } from "@/components/common";
import { Pill } from "@/components/status";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import type { AnswerGradeRow, ContentBrief } from "@/lib/ai";
import { api } from "@/lib/api";

/** Grade a page by URL, or every audited page. */
export function GradeForm() {
  const router = useRouter();
  const [url, setUrl] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const call = async (what: string, fn: () => Promise<{ score?: number | null; status?: string; note?: string | null; graded?: number }>) => {
    setBusy(what);
    try {
      const r = await fn();
      if (r.graded !== undefined) toast.success(`Graded ${r.graded} pages`);
      else if (r.status === "ok") toast.success(`Graded: ${r.score} / 100`);
      else toast.warning("Not graded", { description: r.note ?? undefined });
      setUrl("");
      router.refresh();
    } catch (e) {
      toast.error("Couldn't grade", { description: (e as Error).message });
    } finally {
      setBusy(null);
    }
  };
  return (
    <form
      className="flex flex-wrap items-end gap-2"
      onSubmit={(e) => {
        e.preventDefault();
        if (url.trim()) call("one", () => api("/aeo/grades", { method: "POST", body: { url: url.trim() } }));
      }}
    >
      <div className="flex min-w-64 flex-1 flex-col gap-1">
        <Label htmlFor="grade-url" className="text-xs">
          Page URL
        </Label>
        <Input id="grade-url" type="url" required placeholder="https://brand.com/product-page" value={url} onChange={(e) => setUrl(e.target.value)} />
      </div>
      <Button type="submit" disabled={busy !== null}>
        <Gauge /> {busy === "one" ? "Grading…" : "Grade page"}
      </Button>
      <Button type="button" variant="outline" disabled={busy !== null} onClick={() => call("all", () => api("/aeo/grades/audited", { method: "POST" }))}>
        {busy === "all" ? "Grading…" : "Grade audited pages"}
      </Button>
    </form>
  );
}

export function GradeList({ grades }: { grades: AnswerGradeRow[] }) {
  return (
    <ul className="flex flex-col gap-3">
      {grades.map((g) => {
        const failed = g.checks.filter((c) => !c.passed);
        return (
          <li key={g.id} className="rounded-xl border p-4">
            <details>
              <summary className="flex cursor-pointer list-none flex-wrap items-center justify-between gap-2">
                <div className="min-w-0">
                  <p className="truncate font-medium">{g.title ?? g.url}</p>
                  <a href={g.url} target="_blank" rel="noreferrer" className="inline-flex max-w-full items-center gap-1 truncate text-xs text-muted-foreground hover:underline">
                    {g.url} <ExternalLink className="size-3 shrink-0" />
                  </a>
                </div>
                <div className="flex items-center gap-2">
                  {g.is_demo && <DemoBadge />}
                  {g.status === "ok" ? (
                    <Pill tone={(g.score ?? 0) >= 75 ? "good" : (g.score ?? 0) >= 50 ? "warning" : "critical"} icon={Gauge}>
                      {g.score} / 100
                    </Pill>
                  ) : (
                    <Pill tone="serious">{g.status === "blocked" ? "Blocked" : "Error"}</Pill>
                  )}
                  {g.status === "ok" && <span className="text-xs text-muted-foreground">{failed.length ? `${failed.length} fixes` : "No fixes"}</span>}
                </div>
              </summary>
              {g.note && <p className="mt-2 text-sm text-muted-foreground">{g.note}</p>}
              {g.status === "ok" && (
                <ul className="mt-3 grid gap-2 md:grid-cols-2">
                  {g.checks.map((c) => (
                    <li key={c.key} className="flex gap-2 rounded-lg bg-muted/40 p-2 text-sm">
                      {c.passed ? <CircleCheck className="mt-0.5 size-4 shrink-0 text-good" /> : <CircleX className="mt-0.5 size-4 shrink-0 text-critical" />}
                      <div>
                        <p className="font-medium">
                          {c.label} <span className="text-xs font-normal text-muted-foreground">· {c.points} pts · {c.detail}</span>
                        </p>
                        {c.fix && <p className="text-xs text-muted-foreground">{c.fix}</p>}
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </details>
          </li>
        );
      })}
    </ul>
  );
}

/** Pick a question and brand; build a brief from the app's data; copy or download as Markdown. */
export function BriefBuilder({ brands, skus, suggestions }: { brands: { id: number; name: string }[]; skus: { id: number; name: string; brand_id: number }[]; suggestions: string[] }) {
  const [question, setQuestion] = useState(suggestions[0] ?? "");
  const [brand, setBrand] = useState(String(brands[0]?.id ?? ""));
  const [sku, setSku] = useState("auto");
  const [brief, setBrief] = useState<ContentBrief | null>(null);
  const [busy, setBusy] = useState(false);
  const brandSkus = skus.filter((s) => String(s.brand_id) === brand);
  const download = () => {
    if (!brief) return;
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([brief.markdown], { type: "text/markdown" }));
    a.download = `brief-${brief.brand.toLowerCase()}-${brief.question.toLowerCase().replace(/[^a-z0-9]+/g, "-").slice(0, 50)}.md`;
    a.click();
    URL.revokeObjectURL(a.href);
  };
  return (
    <div className="flex flex-col gap-4">
      <form
        className="grid gap-3 md:grid-cols-[1fr_12rem_16rem_auto] md:items-end"
        onSubmit={async (e) => {
          e.preventDefault();
          setBusy(true);
          try {
            setBrief(await api<ContentBrief>("/aeo/brief", { method: "POST", body: { question, brand_id: Number(brand), sku_id: sku === "auto" ? null : Number(sku) } }));
          } catch (err) {
            toast.error("Couldn't build the brief", { description: (err as Error).message });
          } finally {
            setBusy(false);
          }
        }}
      >
        <div className="flex flex-col gap-1">
          <Label htmlFor="brief-q" className="text-xs">
            Question to win
          </Label>
          <Input id="brief-q" list="brief-suggestions" required minLength={5} value={question} onChange={(e) => setQuestion(e.target.value)} />
          <datalist id="brief-suggestions">
            {suggestions.map((s) => (
              <option key={s} value={s} />
            ))}
          </datalist>
        </div>
        <div className="flex flex-col gap-1">
          <Label className="text-xs">Brand</Label>
          <Select items={brands.map((b) => ({ value: String(b.id), label: b.name }))} value={brand} onValueChange={(v) => { setBrand(String(v)); setSku("auto"); }}>
            <SelectTrigger aria-label="Brand">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {brands.map((b) => (
                <SelectItem key={b.id} value={String(b.id)}>
                  {b.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="flex flex-col gap-1">
          <Label className="text-xs">Product</Label>
          <Select items={[{ value: "auto", label: "Brand's main product" }, ...brandSkus.map((s) => ({ value: String(s.id), label: s.name }))]} value={sku} onValueChange={(v) => setSku(String(v))}>
            <SelectTrigger aria-label="Product">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="auto">Brand&apos;s main product</SelectItem>
              {brandSkus.map((s) => (
                <SelectItem key={s.id} value={String(s.id)}>
                  {s.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <Button type="submit" disabled={busy || !brand}>
          <FileText /> {busy ? "Building…" : "Build brief"}
        </Button>
      </form>

      {brief && (
        <article className="flex flex-col gap-4 rounded-xl border p-4" aria-label="Content brief">
          <div className="flex flex-wrap items-start justify-between gap-2">
            <div>
              <h3 className="font-semibold">{brief.question}</h3>
              <p className="text-sm text-muted-foreground">
                {brief.brand} · {brief.product}
              </p>
            </div>
            <div className="flex gap-2">
              <Button size="sm" variant="outline" onClick={() => navigator.clipboard.writeText(brief.markdown).then(() => toast.success("Brief copied as Markdown"))}>
                <Copy /> Copy
              </Button>
              <Button size="sm" variant="outline" onClick={download}>
                <Download /> Download .md
              </Button>
            </div>
          </div>
          <section>
            <h4 className="text-sm font-medium">Answer first</h4>
            <p className="text-sm">{brief.answer_first}</p>
          </section>
          {brief.emphasise.length > 0 && (
            <section>
              <h4 className="text-sm font-medium">Attributes to make unmistakable</h4>
              <ul className="mt-1 flex flex-col gap-1 text-sm">
                {brief.emphasise.map((e) => (
                  <li key={e.attribute} className="flex flex-wrap items-center gap-2">
                    {e.gap && <Pill tone="serious">Gap</Pill>}
                    <span className="font-medium">{e.attribute}</span>
                    <span className="text-muted-foreground">
                      AI links it to {brief.brand} in {Math.round(e.ai_rate * 100)}% of answers{e.leader && `; ${e.leader} owns it today`}
                    </span>
                  </li>
                ))}
              </ul>
            </section>
          )}
          {brief.facts.length > 0 && (
            <section>
              <h4 className="text-sm font-medium">Approved facts to state</h4>
              <dl className="mt-1 grid grid-cols-[10rem_1fr] gap-x-2 gap-y-1 text-sm">
                {brief.facts.map((f) => (
                  <div key={f.label} className="contents">
                    <dt className="text-muted-foreground">{f.label}</dt>
                    <dd>{Array.isArray(f.value) ? f.value.join(", ") : String(f.value)}</dd>
                  </div>
                ))}
              </dl>
            </section>
          )}
          {brief.correct.length > 0 && (
            <section>
              <h4 className="text-sm font-medium">What AI gets wrong today</h4>
              <ul className="mt-1 list-disc pl-5 text-sm">
                {brief.correct.map((w) => (
                  <li key={w.claim}>
                    {w.claim} <span className="text-muted-foreground">({w.verdict})</span>
                  </li>
                ))}
              </ul>
            </section>
          )}
          <div className="grid gap-4 md:grid-cols-2">
            {brief.related_questions.length > 0 && (
              <section>
                <h4 className="text-sm font-medium">Answer these as H2 questions</h4>
                <ul className="mt-1 list-disc pl-5 text-sm">
                  {brief.related_questions.map((q) => (
                    <li key={q}>{q}</li>
                  ))}
                </ul>
              </section>
            )}
            {brief.sites.length > 0 && (
              <section>
                <h4 className="text-sm font-medium">Earn mentions on</h4>
                <p className="text-xs text-muted-foreground">Sites AI cites when it recommends a competitor instead of you.</p>
                <ul className="mt-1 list-disc pl-5 text-sm">
                  {brief.sites.map((s) => (
                    <li key={s}>{s}</li>
                  ))}
                </ul>
              </section>
            )}
          </div>
          <details>
            <summary className="cursor-pointer text-sm font-medium">Page checklist ({brief.structure.length})</summary>
            <ul className="mt-1 list-disc pl-5 text-sm">
              {brief.structure.map((s) => (
                <li key={s.label}>
                  <span className="font-medium">{s.label}:</span> {s.fix}
                </li>
              ))}
            </ul>
          </details>
        </article>
      )}
    </div>
  );
}
