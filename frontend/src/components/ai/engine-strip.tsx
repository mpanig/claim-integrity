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
        const tone = m.mode === "live" ? "good" : m.mode === "demo" ? "serious" : m.mode === "awaiting" ? "warning" : "neutral";
        const Icon = m.mode === "live" ? Radio : m.mode === "demo" ? FlaskConical : KeyRound;
        const text = {
          live: `live · ${m.answers}`,
          demo: `demo · ${m.answers}`,
          awaiting: "key found, no real answers yet",
          none: "no answers",
        }[m.mode];
        return (
          <li key={m.engine}>
            <Pill tone={tone} icon={Icon} title={s ? `${s.env_key}: ${s.status}` : undefined}>
              {m.label}
              <span className="text-muted-foreground">
                {text}
                {s?.status === "key missing" && m.mode !== "awaiting" && " · key missing"}
              </span>
            </Pill>
          </li>
        );
      })}
    </ul>
  );
}
