"use client";

import { Plus, RefreshCw, Trash2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { api } from "@/lib/api";

function useAction() {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  async function run(fn: () => Promise<unknown>, ok: string) {
    setBusy(true);
    try {
      await fn();
      toast.success(ok);
      router.refresh();
      return true;
    } catch (e) {
      toast.error("That didn't work", { description: (e as Error).message });
      return false;
    } finally {
      setBusy(false);
    }
  }
  return { busy, run };
}

export function RunButton({ path, label, ok }: { path: string; label: string; ok: string }) {
  const { busy, run } = useAction();
  return (
    <Button variant="outline" disabled={busy} onClick={() => run(() => api(path, { method: "POST" }), ok)}>
      <RefreshCw className={busy ? "animate-spin" : undefined} /> {busy ? "Checking…" : label}
    </Button>
  );
}

export function DeleteUrl({ id }: { id: number }) {
  const { busy, run } = useAction();
  return (
    <Button variant="ghost" size="icon-sm" aria-label="Remove from audit" disabled={busy} onClick={() => run(() => api(`/audit/urls/${id}`, { method: "DELETE" }), "Removed")}>
      <Trash2 />
    </Button>
  );
}

export function AddUrl({ brands, skus }: { brands: { id: number; name: string; label?: string | null }[]; skus: { id: number; name: string; brand_id: number }[] }) {
  const { busy, run } = useAction();
  const [url, setUrl] = useState("");
  const [brand, setBrand] = useState(String(brands[0]?.id ?? ""));
  const [sku, setSku] = useState("none");
  const brandItems = brands.map((b) => ({ value: String(b.id), label: b.label ?? b.name }));
  const skuItems = [{ value: "none", label: "Not a product page" }, ...skus.filter((s) => String(s.brand_id) === brand).map((s) => ({ value: String(s.id), label: s.name }))];
  return (
    <form
      className="flex flex-wrap items-center gap-2"
      onSubmit={async (e) => {
        e.preventDefault();
        if (await run(() => api("/audit/urls", { method: "POST", body: { url: url.trim(), brand_id: Number(brand), sku_id: sku === "none" ? null : Number(sku) } }), "Added. Run the audit to check it.")) setUrl("");
      }}
    >
      <Input className="min-w-72 flex-1" type="url" placeholder="https://brand.com/product-page" aria-label="Page URL" value={url} onChange={(e) => setUrl(e.target.value)} />
      <Select items={brandItems} value={brand} onValueChange={(v) => { setBrand(v as string); setSku("none"); }}>
        <SelectTrigger className="w-36" aria-label="Brand">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {brandItems.map((b) => (
            <SelectItem key={b.value} value={b.value}>
              {b.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      <Select items={skuItems} value={sku} onValueChange={(v) => setSku(v as string)}>
        <SelectTrigger className="w-64" aria-label="Product">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {skuItems.map((s) => (
            <SelectItem key={s.value} value={s.value}>
              {s.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      <Button type="submit" disabled={busy || !/^https?:\/\//.test(url.trim())}>
        <Plus /> Add page
      </Button>
    </form>
  );
}
