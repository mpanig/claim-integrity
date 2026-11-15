"use client";

import { Search } from "lucide-react";
import { useEffect, useState } from "react";
import { Input } from "@/components/ui/input";
import { useUrlState } from "@/hooks/use-url-state";

/** Text filter kept in the URL (?q=), debounced. */
export function SearchBox({ placeholder, param = "q" }: { placeholder: string; param?: string }) {
  const { params, set } = useUrlState();
  const current = params.get(param) ?? "";
  const [text, setText] = useState(current);

  useEffect(() => {
    if (text === current) return;
    const t = setTimeout(() => set({ [param]: text.trim() || null }), 300);
    return () => clearTimeout(t);
  }, [text, current, param, set]);

  return (
    <div className="relative w-full max-w-sm">
      <Search className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" />
      <Input
        type="search"
        aria-label={placeholder}
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder={placeholder}
        className="pl-8"
      />
    </div>
  );
}
