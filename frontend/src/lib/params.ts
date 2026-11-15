export type SP = Record<string, string | string[] | undefined>;

export function first(v: string | string[] | undefined): string | undefined {
  return Array.isArray(v) ? v[0] : v;
}

export function all(v: string | string[] | undefined): string[] {
  if (v === undefined) return [];
  return Array.isArray(v) ? v : [v];
}

export function brandParam(sp: SP): number | undefined {
  const b = first(sp.brand);
  return b && /^\d+$/.test(b) ? Number(b) : undefined;
}

export function rangeWeeks(sp: SP): number {
  const r = first(sp.range) ?? "12w";
  const m = /^(\d+)w$/.exec(r);
  return m ? Number(m[1]) : 12;
}
