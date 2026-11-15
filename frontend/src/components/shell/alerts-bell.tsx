"use client";

import { Bell } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";

/** Unread alert count in the top bar; refreshes on navigation and when alerts change. */
export function AlertsBell() {
  const pathname = usePathname();
  const [unread, setUnread] = useState(0);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    const bump = () => setTick((t) => t + 1);
    window.addEventListener("alerts-changed", bump);
    return () => window.removeEventListener("alerts-changed", bump);
  }, []);

  useEffect(() => {
    let cancelled = false;
    api<{ unread: number }>("/alerts", { params: { limit: 1 } })
      .then((r) => !cancelled && setUnread(r.unread))
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [pathname, tick]);

  return (
    <Link
      href="/alerts"
      className="relative flex size-8 items-center justify-center rounded-lg hover:bg-muted"
      aria-label={unread ? `${unread} unread alerts` : "Alerts"}
    >
      <Bell className="size-4" />
      {unread > 0 && (
        <span className="absolute -top-0.5 -right-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-critical px-1 text-[10px] font-semibold text-white tabular-nums">
          {unread > 99 ? "99+" : unread}
        </span>
      )}
    </Link>
  );
}
