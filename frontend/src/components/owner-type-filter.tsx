"use client";

import { Button } from "@/components/ui/button";
import { useUrlState } from "@/hooks/use-url-state";

export function OwnerTypeFilter({ options }: { options: { value: string; label: string; count: number }[] }) {
  const { params, set } = useUrlState();
  const current = params.get("owner_type");
  return (
    <div className="flex flex-wrap gap-1.5" role="group" aria-label="Filter by owner">
      <Button size="sm" variant={current ? "outline" : "default"} onClick={() => set({ owner_type: null })}>
        Everyone
      </Button>
      {options.map((o) => (
        <Button
          key={o.value}
          size="sm"
          variant={current === o.value ? "default" : "outline"}
          aria-pressed={current === o.value}
          onClick={() => set({ owner_type: o.value })}
        >
          {o.label} <span className="tabular-nums opacity-70">{o.count}</span>
        </Button>
      ))}
    </div>
  );
}
