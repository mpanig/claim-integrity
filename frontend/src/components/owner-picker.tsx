"use client";

import { Select, SelectContent, SelectGroup, SelectItem, SelectLabel, SelectTrigger, SelectValue } from "@/components/ui/select";
import { type Role, useTeam } from "@/lib/team";

const NONE = "__none__";

/** Owner dropdown from Settings > Team. Suggested people (matching role) are listed first. */
export function OwnerPicker({
  value,
  onChange,
  disabled,
  suggestRole,
}: {
  value: string | null;
  onChange: (owner: string | null) => void;
  disabled?: boolean;
  suggestRole?: Role;
}) {
  const team = useTeam();
  const members = team?.members ?? [];
  const suggested = suggestRole ? members.filter((m) => m.role === suggestRole) : [];
  const others = members.filter((m) => !suggested.includes(m));
  const known = new Set(members.map((m) => m.name));
  const items = [
    { value: NONE, label: "Unassigned" },
    ...members.map((m) => ({ value: m.name, label: m.name })),
    ...(value && !known.has(value) ? [{ value, label: value }] : []),
  ];

  return (
    <Select
      items={items}
      value={value ?? NONE}
      disabled={disabled || !team}
      onValueChange={(v) => {
        const next = v === NONE ? null : (v as string);
        if (next !== value) onChange(next);
      }}
    >
      <SelectTrigger className="w-full" aria-label="Owner">
        <SelectValue />
      </SelectTrigger>
      <SelectContent alignItemWithTrigger={false} align="start">
        <SelectItem value={NONE}>Unassigned</SelectItem>
        {value && !known.has(value) && <SelectItem value={value}>{value}</SelectItem>}
        {suggested.length > 0 && (
          <SelectGroup>
            <SelectLabel>Suggested</SelectLabel>
            {suggested.map((m) => (
              <SelectItem key={m.id} value={m.name}>
                {m.name}
              </SelectItem>
            ))}
          </SelectGroup>
        )}
        <SelectGroup>
          {suggested.length > 0 && <SelectLabel>Everyone</SelectLabel>}
          {others.map((m) => (
            <SelectItem key={m.id} value={m.name}>
              {m.name} <span className="text-muted-foreground">· {m.role_label}</span>
            </SelectItem>
          ))}
        </SelectGroup>
      </SelectContent>
    </Select>
  );
}
