"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback } from "react";

/** Params that follow the user from page to page. */
export const GLOBAL_PARAMS = ["brand", "range"] as const;

export type ParamUpdate = Record<string, string | string[] | null | undefined>;

export function applyParams(current: URLSearchParams, updates: ParamUpdate): string {
  const next = new URLSearchParams(current);
  for (const [key, value] of Object.entries(updates)) {
    next.delete(key);
    if (Array.isArray(value)) value.forEach((v) => next.append(key, v));
    else if (value !== null && value !== undefined && value !== "") next.set(key, value);
  }
  const s = next.toString();
  return s ? `?${s}` : "";
}

/** Read and write URL search params (filters live in the URL so they can be shared). */
export function useUrlState() {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();

  const set = useCallback(
    (updates: ParamUpdate, mode: "replace" | "push" = "replace") => {
      const url = `${pathname}${applyParams(new URLSearchParams(params.toString()), updates)}`;
      if (mode === "push") router.push(url, { scroll: false });
      else router.replace(url, { scroll: false });
    },
    [params, pathname, router],
  );

  /** A link to `href` that keeps the global params (brand, date range). */
  const carry = useCallback(
    (href: string) => {
      const [path, query = ""] = href.split("?");
      const out = new URLSearchParams(query);
      for (const key of GLOBAL_PARAMS) {
        const v = params.get(key);
        if (v && !out.has(key)) out.set(key, v);
      }
      const s = out.toString();
      return s ? `${path}?${s}` : path;
    },
    [params],
  );

  return { params, set, carry, pathname };
}
