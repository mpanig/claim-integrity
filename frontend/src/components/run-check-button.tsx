"use client";

import { RefreshCw } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import type { RunResult } from "@/lib/types";

export async function runCheck(skuId: number): Promise<RunResult> {
  const r = await api<RunResult>(`/skus/${skuId}/run`, { method: "POST" });
  const parts = [`${r.new} new`, `${r.resolved} resolved`, `${r.reopened} reopened`];
  toast.success("Check finished", {
    description: `${parts.join(" · ")}. Drift score now ${r.drift_score ?? "–"}${r.truth_status === "inferred" ? " (against inferred truth, unverified)" : ""}.`,
  });
  return r;
}

export function RunCheckButton({
  skuId,
  size = "default",
  variant = "outline",
  label = "Run check",
}: {
  skuId: number;
  size?: "default" | "sm" | "xs";
  variant?: "outline" | "default" | "ghost";
  label?: string;
}) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  return (
    <Button
      size={size}
      variant={variant}
      disabled={busy}
      onClick={async () => {
        setBusy(true);
        try {
          await runCheck(skuId);
          router.refresh();
        } catch (e) {
          toast.error("Check failed", { description: (e as Error).message });
        } finally {
          setBusy(false);
        }
      }}
    >
      <RefreshCw className={busy ? "animate-spin" : undefined} />
      {busy ? "Checking…" : label}
    </Button>
  );
}
