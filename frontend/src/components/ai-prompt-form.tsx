"use client";

import { Plus, Trash2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { api } from "@/lib/api";

const ANY = "category";

export function AiPromptForm({ products }: { products: { id: number; name: string }[] }) {
  const router = useRouter();
  const [text, setText] = useState("");
  const [sku, setSku] = useState(ANY);
  const [busy, setBusy] = useState(false);
  const items = [{ value: ANY, label: "General / category question" }, ...products.map((p) => ({ value: String(p.id), label: p.name }))];

  return (
    <form
      className="flex flex-col gap-2 sm:flex-row"
      onSubmit={async (e) => {
        e.preventDefault();
        setBusy(true);
        try {
          await api("/ai-visibility/prompts", {
            method: "POST",
            body: { text, sku_id: sku === ANY ? null : Number(sku) },
          });
          toast.success("Prompt saved", { description: "It will be asked once AI assistants are connected." });
          setText("");
          router.refresh();
        } catch (err) {
          toast.error("Couldn't save the prompt", { description: (err as Error).message });
        } finally {
          setBusy(false);
        }
      }}
    >
      <Input
        aria-label="Question to ask AI assistants"
        placeholder="e.g. Which cleanser is best for eczema-prone skin?"
        value={text}
        onChange={(e) => setText(e.target.value)}
        className="flex-1"
      />
      <Select items={items} value={sku} onValueChange={(v) => setSku(v as string)}>
        <SelectTrigger aria-label="About which product" className="sm:w-64">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {items.map((i) => (
            <SelectItem key={i.value} value={i.value}>
              {i.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      <Button type="submit" disabled={busy || text.trim().length < 5}>
        <Plus /> Track prompt
      </Button>
    </form>
  );
}

export function DeletePromptButton({ id }: { id: number }) {
  const router = useRouter();
  return (
    <Button
      variant="ghost"
      size="icon-sm"
      aria-label="Stop tracking this prompt"
      onClick={async () => {
        try {
          await api(`/ai-visibility/prompts/${id}`, { method: "DELETE" });
          toast.success("Prompt removed");
          router.refresh();
        } catch (err) {
          toast.error("Couldn't remove it", { description: (err as Error).message });
        }
      }}
    >
      <Trash2 />
    </Button>
  );
}
