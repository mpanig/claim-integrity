import { KeyRound } from "lucide-react";
import { RunEngineNow } from "@/components/ai/run-engine-now";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import type { EngineMode, PlanConfig } from "@/lib/ai";
import { serverGet } from "@/lib/api";

/** Engines whose key is set but have no real answers yet: their demo is hidden; offer a pilot run. */
export async function AwaitingEngines({ modes }: { modes: EngineMode[] }) {
  const waiting = modes.filter((m) => m.mode === "awaiting");
  if (!waiting.length) return null;
  const configs = await serverGet<{ id: number; name: string; config: PlanConfig; budget_usd: number }[]>("/ai/configs");
  const pilot = configs.find((c) => /pilot/i.test(c.name)) ?? configs[0] ?? null;
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <KeyRound className="size-4" /> Key found, no real answers yet
        </CardTitle>
        <CardDescription>
          These engines have an API key, so their demo answers no longer show. Run the {pilot ? `"${pilot.name}"` : "pilot"} plan to get real ones.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        {waiting.map((m) => (
          <RunEngineNow key={m.engine} engine={m.engine} label={m.label} plan={pilot?.config ?? null} budget={pilot?.budget_usd ?? 5} />
        ))}
      </CardContent>
    </Card>
  );
}
