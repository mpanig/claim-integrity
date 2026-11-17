"use client";

import { ChevronLeft, ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useUrlState } from "@/hooks/use-url-state";

/** Previous / next for a paged list; the page number lives in the URL (?p=). */
export function Pager({ total, limit, offset, noun = "conflicts" }: { total: number; limit: number; offset: number; noun?: string }) {
  const { set } = useUrlState();
  const page = Math.floor(offset / limit) + 1;
  const pages = Math.max(1, Math.ceil(total / limit));
  const go = (p: number) => {
    set({ p: p <= 1 ? null : String(p) }, "push");
    window.scrollTo({ top: 0 });
  };
  return (
    <nav className="flex flex-wrap items-center justify-between gap-2 text-sm" aria-label="Pages">
      <span className="text-muted-foreground tabular-nums">
        {total === 0 ? `No ${noun}` : `${offset + 1}–${Math.min(offset + limit, total)} of ${total} ${noun}`}
      </span>
      {pages > 1 && (
        <span className="flex items-center gap-1">
          <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => go(page - 1)} aria-label="Previous page">
            <ChevronLeft /> Previous
          </Button>
          <span className="px-2 tabular-nums text-muted-foreground">
            Page {page} of {pages}
          </span>
          <Button variant="outline" size="sm" disabled={page >= pages} onClick={() => go(page + 1)} aria-label="Next page">
            Next <ChevronRight />
          </Button>
        </span>
      )}
    </nav>
  );
}
