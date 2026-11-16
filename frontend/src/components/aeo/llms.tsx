"use client";

import { CircleCheck, CircleX, Copy, Download, FileCode2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { DemoBadge, TimeAgo } from "@/components/common";
import { Pill } from "@/components/status";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { api } from "@/lib/api";

export interface LlmsRow {
  id: number | null;
  host: string;
  brand_id: number | null;
  brand_name: string | null;
  checked_at: string | null;
  status: "found" | "missing" | "blocked" | "error" | "unchecked";
  http_status: number | null;
  score: number | null;
  result: {
    note?: string;
    checks?: { label: string; points: number; passed: boolean; fix: string | null }[];
    sections?: { title: string; links: number }[];
    full_txt?: boolean;
    links?: number;
  };
  is_demo: boolean;
}

const STATUS = {
  found: { tone: "good", text: "Found" },
  missing: { tone: "serious", text: "Missing" },
  blocked: { tone: "neutral", text: "Not fetched" },
  error: { tone: "critical", text: "Error" },
  unchecked: { tone: "neutral", text: "Not checked" },
} as const;

/** Draft an llms.txt for a brand, edit it, then copy or download. */
function Generator({ brandId, brandName }: { brandId: number; brandName: string }) {
  const [text, setText] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  if (text === null)
    return (
      <Button
        size="sm"
        variant="outline"
        disabled={busy}
        onClick={async () => {
          setBusy(true);
          try {
            setText((await api<{ text: string }>(`/aeo/llms/generate/${brandId}`)).text);
          } catch (e) {
            toast.error("Couldn't draft llms.txt", { description: (e as Error).message });
          } finally {
            setBusy(false);
          }
        }}
      >
        <FileCode2 /> {busy ? "Drafting…" : `Draft llms.txt for ${brandName}`}
      </Button>
    );
  return (
    <div className="flex flex-col gap-2">
      <p className="text-xs text-muted-foreground">Draft from your products, approved facts and positioning. Replace the REPLACE links, then publish it at /llms.txt on your site.</p>
      <Textarea aria-label={`llms.txt draft for ${brandName}`} className="min-h-64 font-mono text-xs" value={text} onChange={(e) => setText(e.target.value)} />
      <div className="flex gap-2">
        <Button size="sm" variant="outline" onClick={() => navigator.clipboard.writeText(text).then(() => toast.success("Copied"))}>
          <Copy /> Copy
        </Button>
        <Button
          size="sm"
          variant="outline"
          onClick={() => {
            const a = document.createElement("a");
            a.href = URL.createObjectURL(new Blob([text], { type: "text/plain" }));
            a.download = "llms.txt";
            a.click();
            URL.revokeObjectURL(a.href);
          }}
        >
          <Download /> Download llms.txt
        </Button>
      </div>
    </div>
  );
}

export function LlmsList({ rows }: { rows: LlmsRow[] }) {
  return (
    <ul className="flex flex-col gap-3">
      {rows.map((r) => {
        const s = STATUS[r.status];
        return (
          <li key={r.host} className="flex flex-col gap-3 rounded-xl border p-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <p className="font-medium">
                  {r.host}/llms.txt <span className="text-sm font-normal text-muted-foreground">· {r.brand_name}</span>
                </p>
                <p className="text-xs text-muted-foreground">
                  {r.checked_at ? (
                    <>
                      Checked <TimeAgo iso={r.checked_at} />
                    </>
                  ) : (
                    "Not checked yet"
                  )}
                  {r.status === "found" && ` · ${r.result.links ?? 0} links in ${r.result.sections?.length ?? 0} sections · llms-full.txt ${r.result.full_txt ? "found" : "not found"}`}
                </p>
              </div>
              <div className="flex items-center gap-2">
                {r.is_demo && <DemoBadge />}
                <Pill tone={s.tone}>{s.text}</Pill>
                {r.score !== null && <Pill tone={r.score >= 75 ? "good" : r.score >= 50 ? "warning" : "critical"}>{r.score} / 100</Pill>}
              </div>
            </div>
            {r.result.note && <p className="text-sm text-muted-foreground">{r.result.note}</p>}
            {r.result.checks && (
              <ul className="grid gap-1.5 md:grid-cols-2">
                {r.result.checks.map((c) => (
                  <li key={c.label} className="flex gap-2 text-sm">
                    {c.passed ? <CircleCheck className="mt-0.5 size-4 shrink-0 text-good" /> : <CircleX className="mt-0.5 size-4 shrink-0 text-critical" />}
                    <span>
                      {c.label}
                      {c.fix && <span className="block text-xs text-muted-foreground">{c.fix}</span>}
                    </span>
                  </li>
                ))}
              </ul>
            )}
            {r.brand_id !== null && r.brand_name && <Generator brandId={r.brand_id} brandName={r.brand_name} />}
          </li>
        );
      })}
    </ul>
  );
}
