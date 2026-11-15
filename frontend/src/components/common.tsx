"use client";

import { FlaskConical, Inbox } from "lucide-react";
import Link from "next/link";
import { useSyncExternalStore } from "react";
import { Skeleton } from "@/components/ui/skeleton";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { timeAgo, shortDate } from "@/lib/format";
import { useUrlState } from "@/hooks/use-url-state";
import { cn } from "@/lib/utils";

const noop = () => () => {};

/** True after hydration; false while rendering on the server. */
export function useHydrated() {
  return useSyncExternalStore(
    noop,
    () => true,
    () => false,
  );
}

/** Relative time; the server renders a plain date so the HTML stays deterministic. */
export function TimeAgo({ iso, className }: { iso: string | null | undefined; className?: string }) {
  const hydrated = useHydrated();
  const text = hydrated ? timeAgo(iso) : iso ? shortDate(iso) : "Never";
  return (
    <time suppressHydrationWarning dateTime={iso ?? undefined} title={iso ? new Date(iso).toLocaleString() : undefined} className={className}>
      {text}
    </time>
  );
}

/** Link that keeps the brand and date-range filters. */
export function CarryLink({ href, ...props }: React.ComponentProps<typeof Link> & { href: string }) {
  const { carry } = useUrlState();
  return <Link href={carry(href)} {...props} />;
}

/** Opens the conflict side panel on the current page. */
export function ConflictLink({
  id,
  className,
  children,
}: {
  id: number;
  className?: string;
  children: React.ReactNode;
}) {
  const { set } = useUrlState();
  return (
    <button type="button" className={cn("text-left", className)} onClick={() => set({ conflict: String(id) }, "push")}>
      {children}
    </button>
  );
}

export function EmptyState({
  title,
  children,
  icon: Icon = Inbox,
  action,
}: {
  title: string;
  children?: React.ReactNode;
  icon?: React.ComponentType<{ className?: string }>;
  action?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 rounded-xl border border-dashed px-6 py-10 text-center">
      <Icon className="size-6 text-muted-foreground" />
      <p className="font-medium">{title}</p>
      {children && <div className="max-w-md text-sm text-muted-foreground">{children}</div>}
      {action && <div className="mt-2">{action}</div>}
    </div>
  );
}

export function DemoBadge({ className }: { className?: string }) {
  return (
    <Tooltip>
      <TooltipTrigger
        render={
          <span
            className={cn(
              "inline-flex h-6 items-center gap-1 rounded-full border border-dashed border-serious px-2 text-xs font-medium",
              className,
            )}
          />
        }
      >
        <FlaskConical className="size-3.5 text-serious" />
        Demo data
      </TooltipTrigger>
      <TooltipContent>Generated sample numbers to show the layout. Not real results.</TooltipContent>
    </Tooltip>
  );
}

export function LoadingBlock({ rows = 3, className }: { rows?: number; className?: string }) {
  return (
    <div className={cn("flex flex-col gap-3", className)} aria-busy="true" aria-label="Loading">
      {Array.from({ length: rows }, (_, i) => (
        <Skeleton key={i} className="h-24 w-full rounded-xl" />
      ))}
    </div>
  );
}
