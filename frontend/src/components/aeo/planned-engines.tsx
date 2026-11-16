import { Clock } from "lucide-react";
import { Pill } from "@/components/status";
import type { PlannedEngine } from "@/lib/ai";

/** Planned engines as dashed pills, for the engine strip. */
export function PlannedPills({ planned }: { planned: PlannedEngine[] }) {
  return (
    <ul className="flex flex-wrap gap-2" aria-label="Planned engines">
      {planned.map((p) => (
        <li key={p.engine}>
          <Pill tone="neutral" icon={Clock} className="border-dashed" title={`${p.how} Key: ${p.env_key}`}>
            {p.label}
            <span className="text-muted-foreground">{p.key_set ? "key set, coming" : "planned"}</span>
          </Pill>
        </li>
      ))}
    </ul>
  );
}

/** Planned engines with how each will connect and which key switches it on. */
export function PlannedList({ planned }: { planned: PlannedEngine[] }) {
  return (
    <ul className="flex flex-col gap-2 text-sm">
      {planned.map((p) => (
        <li key={p.engine} className="flex flex-col gap-0.5 rounded-lg border border-dashed p-2">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-medium">{p.label}</span>
            <span className="text-xs text-muted-foreground">{p.env_key}</span>
            <Pill tone={p.key_set ? "warning" : "neutral"} icon={Clock}>
              {p.key_set ? "Key set, connector coming" : "Planned"}
            </Pill>
            {!p.official_api && <Pill tone="neutral">No official API</Pill>}
          </div>
          <p className="text-xs text-muted-foreground">{p.how}</p>
        </li>
      ))}
    </ul>
  );
}
