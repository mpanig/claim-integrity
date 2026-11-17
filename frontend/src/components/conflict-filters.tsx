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
const SEVERITY_ITEMS = [
  { value: ANY, label: "Any risk" },
  { value: "9", label: "High risk only (9–10)" },
  { value: "4", label: "Medium and high (4+)" },
];

/** Filters for conflict lists. All state lives in the URL so a view can be shared; any change goes back to page 1.
 * The board has its own status columns, so it hides the status and owner filters. */
export function ConflictFilters({ owners = [], board = false }: { owners?: string[]; board?: boolean }) {
  const { params, set } = useUrlState();
  const status = params.get("status") ?? "unresolved";
  const verdict = params.get("verdict") ?? ANY;
  const owner = params.get("owner") ?? ANY;
  const sev = params.get("sev") ?? ANY;
  const ownerItems = [{ value: ANY, label: "Any owner" }, ...owners.map((o) => ({ value: o, label: o }))];
  const filtered = params.has("status") || params.has("verdict") || params.has("owner") || params.has("sev");
  const change = (u: Record<string, string | null>) => set({ ...u, p: null, show: null });

  return (
    <div className="flex flex-wrap items-center gap-2">
      {!board && <FilterSelect label="Status" items={STATUS_ITEMS} value={status} onChange={(v) => change({ status: v === "unresolved" ? null : v })} />}
      <FilterSelect label="Risk" items={SEVERITY_ITEMS} value={sev} onChange={(v) => change({ sev: v === ANY ? null : v })} />
      <FilterSelect label="Issue type" items={VERDICT_ITEMS} value={verdict} onChange={(v) => change({ verdict: v === ANY ? null : v })} />
      {!board && <FilterSelect label="Owner" items={ownerItems} value={owner} onChange={(v) => change({ owner: v === ANY ? null : v })} />}
      {filtered && (
        <Button variant="ghost" size="sm" onClick={() => change({ status: null, verdict: null, owner: null, sev: null })}>
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
