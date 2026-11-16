"use client";

import { useUrlState } from "@/hooks/use-url-state";
import { cn } from "@/lib/utils";
import Link from "next/link";

const TABS = [
  { href: "/ai-visibility", label: "Overview" },
  { href: "/ai-visibility/coverage", label: "Coverage" },
  { href: "/ai-visibility/answers", label: "Answers" },
  { href: "/ai-visibility/plan", label: "Test plan" },
  { href: "/ai-visibility/library", label: "Library" },
];

export function AiTabs() {
  const { pathname, carry } = useUrlState();
  return (
    <nav className="no-print flex gap-1 border-b" aria-label="AI visibility sections">
      {TABS.map((t) => {
        const active = pathname === t.href;
        return (
          <Link
            key={t.href}
            href={carry(t.href)}
            aria-current={active ? "page" : undefined}
            className={cn(
              "-mb-px border-b-2 px-3 py-2 text-sm text-muted-foreground hover:text-foreground",
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
