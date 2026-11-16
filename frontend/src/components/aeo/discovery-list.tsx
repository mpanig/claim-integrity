"use client";

import { Plus, Sparkles } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";
import { Pill } from "@/components/status";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useUrlState } from "@/hooks/use-url-state";
import { type Discovery, INTENT_LABEL } from "@/lib/ai";
import { api } from "@/lib/api";

/** Suggested prompts: filter by question type, add to the library, ask Claude for more. */
export function DiscoveryList({ data }: { data: Discovery }) {
  const router = useRouter();
  const { set } = useUrlState();
  const [intent, setIntent] = useState<string>("all");
  const [added, setAdded] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState<string | null>(null);
  const intents = [...new Set(data.candidates.map((c) => c.intent))];
  const rows = data.candidates.filter((c) => (intent === "all" || c.intent === intent) && !added.has(c.id));

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-2">
        <div className="flex flex-wrap gap-1" role="group" aria-label="Question type">
          {["all", ...intents].map((i) => (
            <Button key={i} size="sm" variant={intent === i ? "default" : "outline"} onClick={() => setIntent(i)} aria-pressed={intent === i}>
              {i === "all" ? `All (${data.candidates.length})` : `${INTENT_LABEL[i] ?? i} (${data.candidates.filter((c) => c.intent === i).length})`}
            </Button>
          ))}
        </div>
        <div className="ml-auto">
          <Button
            size="sm"
            variant="outline"
            disabled={data.llm === "no key" || data.llm === "used"}
            title={data.llm === "no key" ? "Add ANTHROPIC_API_KEY to backend/.env to use Claude" : "One Claude call, a few cents"}
            onClick={() => set({ llm: "1" }, "push")}
          >
            <Sparkles /> {data.llm === "used" ? "Claude suggestions added" : "Suggest more with Claude"}
          </Button>
        </div>
      </div>
      {data.llm.startsWith("error") && <p className="text-sm text-critical">Claude suggestions failed ({data.llm.slice(7)}). Rule-based suggestions are still shown.</p>}
      <div className="overflow-x-auto">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-28">Importance (est.)</TableHead>
              <TableHead>Question</TableHead>
              <TableHead>Type</TableHead>
              <TableHead>Why</TableHead>
              <TableHead className="w-24" />
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((c) => (
              <TableRow key={c.id}>
                <TableCell>
                  <div className="flex items-center gap-2">
                    <div className="h-1.5 w-14 rounded-full bg-muted" aria-hidden>
                      <div className="h-1.5 rounded-full bg-[var(--series-1)]" style={{ width: `${c.importance}%` }} />
                    </div>
                    <span className="tabular-nums">{c.importance}</span>
                  </div>
                </TableCell>
                <TableCell className="max-w-96 font-medium whitespace-normal">
                  {c.text}
                  {c.source === "claude" && (
                    <Pill tone="neutral" className="ml-2" icon={Sparkles}>
                      Claude
                    </Pill>
                  )}
                </TableCell>
                <TableCell className="text-muted-foreground">{INTENT_LABEL[c.intent] ?? c.intent}</TableCell>
                <TableCell className="max-w-96 text-xs whitespace-normal text-muted-foreground">
                  <ul className="flex flex-col gap-0.5">
                    {c.reasons.map((r) => (
                      <li key={r}>{r}</li>
                    ))}
                  </ul>
                </TableCell>
                <TableCell>
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={busy === c.id}
                    onClick={async () => {
                      setBusy(c.id);
                      try {
                        await api("/ai/prompts", {
                          method: "POST",
                          body: { text: c.text, intent: c.intent, funnel_stage: c.funnel_stage, sku_id: c.sku_id, category: c.category, competitor: c.competitor },
                        });
                        setAdded((prev) => new Set(prev).add(c.id));
                        toast.success("Added to the prompt library", { description: "Include it in a test plan to start measuring it." });
                        router.refresh();
                      } catch (e) {
                        toast.error("Couldn't add it", { description: (e as Error).message });
                      } finally {
                        setBusy(null);
                      }
                    }}
                  >
                    <Plus /> Add
                  </Button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
