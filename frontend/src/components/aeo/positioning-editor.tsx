"use client";

import { Save } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { api } from "@/lib/api";

/** Pick the attributes a brand wants AI answers to associate with it. */
export function PositioningEditor({
  brandId,
  brandName,
  attributes,
  initial,
}: {
  brandId: number;
  brandName: string;
  attributes: { key: string; label: string; polarity: string }[];
  initial: string[];
}) {
  const router = useRouter();
  const [chosen, setChosen] = useState(new Set(initial));
  const [busy, setBusy] = useState(false);
  const changed = chosen.size !== initial.length || initial.some((k) => !chosen.has(k));
  return (
    <fieldset className="flex flex-col gap-2">
      <legend className="mb-1 text-sm font-medium">Intended positioning for {brandName}</legend>
      <div className="grid gap-1.5 sm:grid-cols-2">
        {attributes
          .filter((a) => a.polarity === "positive")
          .map((a) => (
            <label key={a.key} className="flex items-center gap-2 text-sm">
              <Checkbox
                checked={chosen.has(a.key)}
                onCheckedChange={(on) =>
                  setChosen((prev) => {
                    const next = new Set(prev);
                    if (on) next.add(a.key);
                    else next.delete(a.key);
                    return next;
                  })
                }
              />
              {a.label}
            </label>
          ))}
      </div>
      <div>
        <Button
          size="sm"
          variant="outline"
          disabled={!changed || busy}
          onClick={async () => {
            setBusy(true);
            try {
              await api(`/ai/brands/${brandId}/positioning`, { method: "PUT", body: { attributes: [...chosen] } });
              toast.success(`Positioning saved for ${brandName}`);
              router.refresh();
            } catch (e) {
              toast.error("Couldn't save", { description: (e as Error).message });
            } finally {
              setBusy(false);
            }
          }}
        >
          <Save /> Save positioning
        </Button>
      </div>
    </fieldset>
  );
}
