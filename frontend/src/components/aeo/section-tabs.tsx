"use client";

import Link from "next/link";
import { useUrlState } from "@/hooks/use-url-state";
import { cn } from "@/lib/utils";

/** In-page tabs for one AEO subsection (each tab is its own route). */
export function SectionTabs({ label, tabs }: { label: string; tabs: { href: string; label: string }[] }) {
  const { pathname, carry } = useUrlState();
  return (
    <nav className="no-print flex gap-1 overflow-x-auto border-b" aria-label={label}>
      {tabs.map((t) => {
        const active = pathname === t.href;
        return (
          <Link
            key={t.href}
            href={carry(t.href)}
            aria-current={active ? "page" : undefined}
            className={cn(
              "-mb-px border-b-2 px-3 py-2 text-sm whitespace-nowrap text-muted-foreground hover:text-foreground",
              active ? "border-foreground font-medium text-foreground" : "border-transparent",
            )}
          >
            {t.label}
          </Link>
        );
      })}
    </nav>
  );
}
