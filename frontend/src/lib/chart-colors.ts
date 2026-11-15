/** Categorical slots in fixed order (validated reference palette, see globals.css).
 * Colour follows the entity: brands are coloured by id order, whatever is filtered.
 * Past four series, fold into "Other" rather than generating new hues. */
export const SERIES = ["var(--series-1)", "var(--series-2)", "var(--series-3)", "var(--series-4)"];

export function brandColorMap(brands: { id: number }[]): Record<string, string> {
  return Object.fromEntries(
    [...brands].sort((a, b) => a.id - b.id).map((b, i) => [String(b.id), SERIES[Math.min(i, SERIES.length - 1)]]),
  );
}
