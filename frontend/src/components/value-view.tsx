import { cn } from "@/lib/utils";

/** Renders an approved or page value. List items in `highlight` are marked as differences. */
export function ValueView({
  value,
  highlight = [],
  tone = "critical",
  empty = "Nothing shown",
}: {
  value: unknown;
  highlight?: string[];
  tone?: "critical" | "good";
  empty?: string;
}) {
  if (value === null || value === undefined || value === "" || (Array.isArray(value) && value.length === 0)) {
    return <p className="text-sm text-muted-foreground italic">{empty}</p>;
  }
  if (Array.isArray(value)) {
    const marks = new Set(highlight.map((h) => h.toLowerCase()));
    return (
      <ul className="flex flex-wrap gap-1.5">
        {value.map((item, i) => {
          const marked = marks.has(String(item).toLowerCase());
          return (
            <li
              key={`${item}-${i}`}
              className={cn(
                "rounded-md border px-1.5 py-0.5 text-xs",
                marked && tone === "critical" && "border-critical/50 bg-critical/10 font-medium",
                marked && tone === "good" && "border-good/50 bg-good/10 font-medium",
              )}
            >
              {marked && <span className="sr-only">Difference: </span>}
              {String(item)}
            </li>
          );
        })}
      </ul>
    );
  }
  if (typeof value === "object") {
    const v = value as { value?: unknown; claim?: string; ingredients?: string[] };
    if ("value" in v) return <ValueView value={v.value} highlight={highlight} tone={tone} />;
    if (v.claim) return <p className="text-sm">&ldquo;{v.claim}&rdquo;</p>;
  }
  return <p className="text-sm">&ldquo;{String(value)}&rdquo;</p>;
}
