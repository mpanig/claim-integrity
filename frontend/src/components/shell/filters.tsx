"use client";

import { CalendarRange, Tags } from "lucide-react";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useUrlState } from "@/hooks/use-url-state";
import type { Brand } from "@/lib/types";
import { DEFAULT_RANGE, RANGES } from "./nav";

const ALL = "all";

export function BrandSwitcher({ brands }: { brands: Brand[] }) {
  const { params, set } = useUrlState();
  const value = params.get("brand") ?? ALL;
  const items = [{ value: ALL, label: "All brands" }, ...brands.map((b) => ({ value: String(b.id), label: b.name }))];
  return (
    <Select items={items} value={value} onValueChange={(v) => set({ brand: v === ALL ? null : (v as string) })}>
      <SelectTrigger aria-label="Brand" className="w-40">
        <Tags className="size-4 text-muted-foreground" />
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

export function RangePicker() {
  const { params, set } = useUrlState();
  const value = params.get("range") ?? DEFAULT_RANGE;
  return (
    <Select
      items={RANGES.map((r) => ({ ...r }))}
      value={value}
      onValueChange={(v) => set({ range: v === DEFAULT_RANGE ? null : (v as string) })}
    >
      <SelectTrigger aria-label="Date range" className="hidden w-44 sm:flex">
        <CalendarRange className="size-4 text-muted-foreground" />
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {RANGES.map((r) => (
          <SelectItem key={r.value} value={r.value}>
            {r.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
