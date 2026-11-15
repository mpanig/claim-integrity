"use client";

import { useState } from "react";
import { Input } from "@/components/ui/input";

/** Free-text owner for now; becomes a team-member dropdown once Settings > Team exists. */
export function OwnerPicker({
  value,
  onChange,
  disabled,
}: {
  value: string | null;
  onChange: (owner: string | null) => void;
  disabled?: boolean;
}) {
  const [text, setText] = useState(value ?? "");
  return (
    <Input
      value={text}
      disabled={disabled}
      placeholder="Unassigned"
      onChange={(e) => setText(e.target.value)}
      onBlur={() => {
        const next = text.trim() || null;
        if (next !== value) onChange(next);
      }}
    />
  );
}
