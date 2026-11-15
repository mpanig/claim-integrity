"use client";

import { Save, Trash2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import { toast } from "sonner";
import { runCheck } from "@/components/run-check-button";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { useUrlState } from "@/hooks/use-url-state";
import { api } from "@/lib/api";
import { FIELD_LABEL } from "@/lib/labels";
import type { Brand, Claim, Field, Sku } from "@/lib/types";

const LIST_FIELDS: { field: Exclude<Field, "name">; help: string; placeholder: string }[] = [
  {
    field: "ingredients",
    help: "One ingredient per line, in INCI order. You can also paste a comma-separated list.",
    placeholder: "Aqua/Water/Eau\nGlycerin\n…",
  },
  { field: "free_from", help: "One claim per line, worded exactly as approved.", placeholder: "Free of Added Fragrance" },
  { field: "claims", help: "Other approved claims, one per line.", placeholder: "Non-comedogenic" },
  { field: "seals", help: "Seals, certifications and endorsements, one per line.", placeholder: "NEA Seal of Acceptance" },
];

function toLines(value: unknown): string {
  return Array.isArray(value) ? value.join("\n") : "";
}

function fromLines(text: string): string[] {
  const lines = text.split("\n").map((l) => l.trim()).filter(Boolean);
  // A single pasted line with commas is an INCI list.
  if (lines.length === 1 && lines[0].includes(",")) return lines[0].split(",").map((s) => s.trim()).filter(Boolean);
  return lines;
}

const NEW_BRAND = "__new__";

export function TruthSheetForm({ sku, claims, brands }: { sku?: Sku; claims?: Claim[]; brands?: Brand[] }) {
  const router = useRouter();
  const { carry } = useUrlState();
  const initial = useMemo(() => {
    const byField = Object.fromEntries((claims ?? []).map((c) => [c.field, c.value])) as Partial<Record<Field, unknown>>;
    return {
      name: (byField.name as string | undefined) ?? sku?.name ?? "",
      ingredients: toLines(byField.ingredients),
      free_from: toLines(byField.free_from),
      claims: toLines(byField.claims),
      seals: toLines(byField.seals),
    } as Record<Field, string>;
  }, [claims, sku]);
  const approved = useMemo(() => new Set((claims ?? []).map((c) => c.field)), [claims]);

  const [values, setValues] = useState(initial);
  const [evidence, setEvidence] = useState(claims?.find((c) => c.evidence_url)?.evidence_url ?? "");
  const [brandChoice, setBrandChoice] = useState<string>(brands?.[0] ? String(brands[0].id) : NEW_BRAND);
  const [newBrand, setNewBrand] = useState("");
  const [gtin, setGtin] = useState(sku?.gtin ?? "");
  const [line, setLine] = useState(sku?.line ?? "");
  const [busy, setBusy] = useState(false);

  const dirty = (Object.keys(values) as Field[]).filter((f) => values[f].trim() !== initial[f].trim());
  const isNew = !sku;

  async function saveExisting() {
    if (!sku) return;
    setBusy(true);
    try {
      for (const f of dirty) {
        const text = values[f];
        if (f !== "name" && f !== "ingredients" && !text.trim()) {
          if (approved.has(f)) await api(`/skus/${sku.id}/claims/${f}`, { method: "DELETE" });
          continue;
        }
        await api(`/skus/${sku.id}/claims/${f}`, {
          method: "PUT",
          body: { value: f === "name" ? text.trim() : fromLines(text), evidence_url: evidence || null },
        });
      }
      if (gtin !== (sku.gtin ?? "") || line !== (sku.line ?? "")) {
        await api(`/skus/${sku.id}`, { method: "PATCH", body: { gtin: gtin || null, line: line || null } });
      }
      toast.success("Truth sheet saved", {
        description: "Re-check the product to compare its pages against the new claims.",
        action: { label: "Run check", onClick: () => runCheck(sku.id).then(() => router.refresh()) },
      });
      router.refresh();
    } catch (e) {
      toast.error("Couldn't save", { description: (e as Error).message });
    } finally {
      setBusy(false);
    }
  }

  async function create() {
    setBusy(true);
    try {
      const claimsBody: Record<string, unknown> = {};
      for (const { field } of LIST_FIELDS) {
        const items = fromLines(values[field]);
        if (items.length) claimsBody[field] = items;
      }
      const created = await api<Sku>("/skus", {
        method: "POST",
        body: {
          name: values.name,
          brand_id: brandChoice === NEW_BRAND ? null : Number(brandChoice),
          brand_name: brandChoice === NEW_BRAND ? newBrand : null,
          gtin: gtin || null,
          line: line || null,
          claims: claimsBody,
          evidence_url: evidence || null,
        },
      });
      toast.success("Product added");
      router.push(carry(`/products/${created.id}`));
    } catch (e) {
      toast.error("Couldn't add the product", { description: (e as Error).message });
      setBusy(false);
    }
  }

  const canCreate = values.name.trim() && fromLines(values.ingredients).length > 0 && (brandChoice !== NEW_BRAND || newBrand.trim());
  const brandItems = [...(brands ?? []).map((b) => ({ value: String(b.id), label: b.name })), { value: NEW_BRAND, label: "New brand…" }];

  return (
    <form
      className="flex flex-col gap-4"
      onSubmit={(e) => {
        e.preventDefault();
        if (isNew) create();
        else saveExisting();
      }}
    >
      <Card>
        <CardHeader>
          <CardTitle>Product</CardTitle>
          <CardDescription>The approved product name is what every page should use.</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4 sm:grid-cols-2">
          {isNew && (
            <div className="flex flex-col gap-1.5">
              <Label>Brand</Label>
              <Select items={brandItems} value={brandChoice} onValueChange={(v) => setBrandChoice(v as string)}>
                <SelectTrigger className="w-full">
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
              {brandChoice === NEW_BRAND && (
                <Input aria-label="New brand name" placeholder="Brand name" value={newBrand} onChange={(e) => setNewBrand(e.target.value)} />
              )}
            </div>
          )}
          <div className="flex flex-col gap-1.5 sm:col-span-1">
            <Label htmlFor="name">{FIELD_LABEL.name}</Label>
            <Input id="name" required value={values.name} onChange={(e) => setValues({ ...values, name: e.target.value })} />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="gtin">GTIN (barcode)</Label>
            <Input id="gtin" inputMode="numeric" maxLength={14} value={gtin} onChange={(e) => setGtin(e.target.value)} placeholder="Optional" />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="line">Product line</Label>
            <Input id="line" value={line} onChange={(e) => setLine(e.target.value)} placeholder="Optional" />
          </div>
          <div className="flex flex-col gap-1.5 sm:col-span-2">
            <Label htmlFor="evidence">Source of truth (URL)</Label>
            <Input
              id="evidence"
              type="url"
              value={evidence}
              onChange={(e) => setEvidence(e.target.value)}
              placeholder="https://brand.com/product-page"
            />
          </div>
        </CardContent>
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        {LIST_FIELDS.map(({ field, help, placeholder }) => (
          <Card key={field}>
            <CardHeader>
              <CardTitle className="flex items-center justify-between gap-2">
                <Label htmlFor={field} className="text-base">
                  {FIELD_LABEL[field]}
                </Label>
                <span className="text-xs font-normal text-muted-foreground">{fromLines(values[field]).length} items</span>
              </CardTitle>
              <CardDescription>{help}</CardDescription>
            </CardHeader>
            <CardContent className="flex flex-col gap-2">
              <Textarea
                id={field}
                rows={field === "ingredients" ? 10 : 4}
                value={values[field]}
                placeholder={placeholder}
                onChange={(e) => setValues({ ...values, [field]: e.target.value })}
              />
              {!isNew && field !== "ingredients" && approved.has(field) && (
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  className="w-fit"
                  onClick={() => setValues({ ...values, [field]: "" })}
                >
                  <Trash2 /> Clear (removes approval on save)
                </Button>
              )}
            </CardContent>
          </Card>
        ))}
      </div>

      <div className="sticky bottom-4 flex flex-wrap items-center justify-end gap-3 rounded-xl border bg-background/95 p-3 shadow-sm backdrop-blur">
        {!isNew && <span className="mr-auto text-sm text-muted-foreground">{dirty.length ? `${dirty.length} unsaved change${dirty.length === 1 ? "" : "s"}` : "No unsaved changes"}</span>}
        {isNew && <span className="mr-auto text-sm text-muted-foreground">A name, brand and ingredient list are required.</span>}
        <Button type="submit" disabled={busy || (isNew ? !canCreate : dirty.length === 0 && gtin === (sku?.gtin ?? "") && line === (sku?.line ?? ""))}>
          <Save /> {isNew ? "Add product" : "Save truth sheet"}
        </Button>
      </div>
    </form>
  );
}
