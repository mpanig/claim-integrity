"use client";

import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import { useUrlState } from "@/hooks/use-url-state";
import { STATUS_LABEL, VERDICT_LABEL, VERDICT_ORDER } from "@/lib/labels";
import type { Status } from "@/lib/types";

const ANY = "any";
const STATUS_ITEMS = [
  { value: "unresolved", label: "Unresolved (to review, accepted, fixed)" },
  { value: ANY, label: "Any status" },
  ...(["open", "accepted", "fixed", "verified", "dismissed"] as Status[]).map((s) => ({ value: s, label: STATUS_LABEL[s] })),
];
const VERDICT_ITEMS = [{ value: ANY, label: "Any type" }, ...VERDICT_ORDER.map((v) => ({ value: v, label: VERDICT_LABEL[v] }))];

/** Filters for the conflicts table. All state lives in the URL so a view can be shared. */
export function ConflictFilters({ owners }: { owners: string[] }) {
  const { params, set } = useUrlState();
  const status = params.get("status") ?? "unresolved";
  const verdict = params.get("verdict") ?? ANY;
  const owner = params.get("owner") ?? ANY;
  const ownerItems = [{ value: ANY, label: "Any owner" }, ...owners.map((o) => ({ value: o, label: o }))];
  const filtered = params.has("status") || params.has("verdict") || params.has("owner");

  return (
    <div className="flex flex-wrap items-center gap-2">
      <FilterSelect label="Status" items={STATUS_ITEMS} value={status} onChange={(v) => set({ status: v === "unresolved" ? null : v })} />
      <FilterSelect label="Issue type" items={VERDICT_ITEMS} value={verdict} onChange={(v) => set({ verdict: v === ANY ? null : v })} />
      <FilterSelect label="Owner" items={ownerItems} value={owner} onChange={(v) => set({ owner: v === ANY ? null : v })} />
      {filtered && (
        <Button variant="ghost" size="sm" onClick={() => set({ status: null, verdict: null, owner: null })}>
          Clear filters
        </Button>
      )}
    </div>
  );
}

function FilterSelect({
  label,
  items,
  value,
  onChange,
}: {
  label: string;
  items: { value: string; label: string }[];
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <Select items={items} value={value} onValueChange={(v) => onChange(v as string)}>
      <SelectTrigger aria-label={label} className="min-w-40">
        <SelectValue />
      </SelectTrigger>
      <SelectContent alignItemWithTrigger={false} align="start">
        {items.map((i) => (
          <SelectItem key={i.value} value={i.value}>
            {i.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
