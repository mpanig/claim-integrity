"use client";

import { Search } from "lucide-react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";

/** Search box in the top bar. Enter opens results; Ctrl/Cmd+K focuses it. */
export function GlobalSearch() {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const [text, setText] = useState(pathname === "/search" ? (params.get("q") ?? "") : "");
  const input = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        input.current?.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  return (
    <form
      role="search"
      className="relative ml-auto hidden w-full max-w-xs md:block"
      onSubmit={(e) => {
        e.preventDefault();
        const q = text.trim();
        if (q.length < 2) return;
        const next = new URLSearchParams();
        next.set("q", q);
        const brand = params.get("brand");
        if (brand) next.set("brand", brand);
        router.push(`/search?${next.toString()}`);
      }}
    >
      <Search className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" />
      <input
        ref={input}
        type="search"
        value={text}
        onChange={(e) => setText(e.target.value)}
        aria-label="Search products, pages and conflicts"
        placeholder="Search products, pages, issues…"
        className="h-8 w-full rounded-lg border border-input bg-transparent pr-12 pl-8 text-sm outline-none placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
      />
      <kbd className="pointer-events-none absolute top-1/2 right-2 -translate-y-1/2 rounded border px-1 text-[10px] text-muted-foreground">
        Ctrl K
      </kbd>
    </form>
  );
}
