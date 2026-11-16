"use client";

import { useUrlState } from "@/hooks/use-url-state";
import { cn } from "@/lib/utils";

export function AnswerLink({ id, className, children }: { id: number; className?: string; children: React.ReactNode }) {
  const { set } = useUrlState();
  return (
    <button type="button" className={cn("text-left", className)} onClick={() => set({ answer: String(id) }, "push")}>
      {children}
    </button>
  );
}

export function ViewToggle({ view }: { view: "list" | "compare" }) {
  const { set } = useUrlState();
  return (
    <div className="inline-flex rounded-lg border p-0.5" role="group" aria-label="View">
      {(["list", "compare"] as const).map((v) => (
        <button
          key={v}
          type="button"
          aria-pressed={view === v}
          onClick={() => set({ view: v === "list" ? null : v })}
          className={cn("rounded-md px-3 py-1 text-sm", view === v ? "bg-muted font-medium" : "text-muted-foreground")}
        >
          {v === "list" ? "List" : "Compare side by side"}
        </button>
      ))}
    </div>
  );
}
