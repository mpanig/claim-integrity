"use client";

import { Play } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { EngineName, Estimate, PlanConfig } from "@/lib/ai";
import { api } from "@/lib/api";

/** Key found, no real answers yet: run the saved pilot plan for this engine only.
 * Shows the estimate and a budget cap before anything is spent. */
export function RunEngineNow({ engine, label, plan, budget }: { engine: EngineName; label: string; plan: PlanConfig | null; budget: number }) {
  const router = useRouter();
  const [est, setEst] = useState<Estimate | null>(null);
  const [cap, setCap] = useState(budget);
  const [busy, setBusy] = useState(false);
  const config = plan ? { ...plan, engines: plan.engines.filter((e) => e.engine === engine) } : null;
  const cfgKey = JSON.stringify(config);

  useEffect(() => {
    if (!config || !config.engines.length) return;
    let cancelled = false;
    api<Estimate>("/ai/estimate", { method: "POST", body: { config, budget_usd: cap } })
      .then((e) => !cancelled && setEst(e))
      .catch(() => {});
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cfgKey]);

  if (!config || !config.engines.length)
    return <p className="text-sm text-muted-foreground">No saved plan includes {label}. Add it in Test plan, then run.</p>;
  return (
    <div className="flex flex-col gap-2 rounded-xl border p-3">
      <p className="text-sm">
        <span className="font-medium">{label}</span>: key found, no real answers yet. Its demo answers are hidden.
      </p>
      <p className="text-sm text-muted-foreground" aria-live="polite">
        {est
          ? `The pilot plan for ${label} is ${est.runnable_calls} answers, about $${est.est_usd.toFixed(2)}. The run stops at the budget cap.`
          : "Estimating cost…"}
      </p>
      <div className="flex flex-wrap items-end gap-2">
        <div className="flex flex-col gap-1">
          <Label htmlFor={`cap-${engine}`} className="text-xs">
            Budget cap (USD)
          </Label>
          <Input id={`cap-${engine}`} type="number" min={0.5} step={0.5} className="w-28" value={cap} onChange={(e) => setCap(Number(e.target.value) || 1)} />
        </div>
        <Button
          disabled={busy || !est || est.runnable_calls === 0}
          onClick={async () => {
            setBusy(true);
            try {
              const r = await api<{ id: number }>("/ai/runs", { method: "POST", body: { config, budget_usd: cap } });
              toast.success(`Run ${r.id} started for ${label}`, { description: "Answers appear here as they arrive; refresh to update." });
              router.refresh();
            } catch (e) {
              toast.error("Couldn't start the run", { description: (e as Error).message });
            } finally {
              setBusy(false);
            }
          }}
        >
          <Play /> Run now
        </Button>
      </div>
    </div>
  );
}
