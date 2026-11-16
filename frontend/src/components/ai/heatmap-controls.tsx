"use client";

import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useUrlState } from "@/hooks/use-url-state";

export function HeatmapControls({ brands, brand, metric }: { brands: string[]; brand: string; metric: string }) {
  const { set } = useUrlState();
  const metrics = [
    { value: "mention", label: "Mentioned" },
    { value: "recommended", label: "Recommended" },
  ];
  const brandItems = brands.map((b) => ({ value: b, label: b }));
  return (
    <div className="flex flex-wrap gap-2">
      <Select items={brandItems} value={brand} onValueChange={(v) => set({ hm_brand: v as string })}>
        <SelectTrigger aria-label="Brand" className="w-44">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {brandItems.map((b) => (
            <SelectItem key={b.value} value={b.value}>
              {b.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      <Select items={metrics} value={metric} onValueChange={(v) => set({ hm_metric: v as string })}>
        <SelectTrigger aria-label="Measure" className="w-40">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {metrics.map((m) => (
            <SelectItem key={m.value} value={m.value}>
              {m.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}
