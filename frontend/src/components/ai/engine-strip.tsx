import { FlaskConical, KeyRound, Radio } from "lucide-react";
import { Pill } from "@/components/status";
import type { EngineMode, EngineStatus } from "@/lib/ai";

/** Per engine: live answers, demo answers, or nothing yet; plus whether its key is set. */
export function EngineStrip({ modes, statuses }: { modes: EngineMode[]; statuses: EngineStatus[] }) {
  const status = Object.fromEntries(statuses.map((s) => [s.engine, s]));
  return (
    <ul className="flex flex-wrap gap-2" aria-label="Engines">
      {modes.map((m) => {
        const s = status[m.engine];
        const tone = m.mode === "live" ? "good" : m.mode === "demo" ? "serious" : "neutral";
        const Icon = m.mode === "live" ? Radio : m.mode === "demo" ? FlaskConical : KeyRound;
        return (
          <li key={m.engine}>
            <Pill tone={tone} icon={Icon} title={s ? `${s.env_key}: ${s.status}` : undefined}>
              {m.label}
              <span className="text-muted-foreground">
                {m.mode === "live" ? `live · ${m.answers}` : m.mode === "demo" ? `demo · ${m.answers}` : "no answers"}
                {s?.status === "key missing" && " · key missing"}
              </span>
            </Pill>
          </li>
        );
      })}
    </ul>
  );
}
