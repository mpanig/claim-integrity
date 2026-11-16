"use client";

import { ImageUp, Save, X } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api } from "@/lib/api";

export interface Branding {
  agency_name: string | null;
  report_title: string;
  primary_color: string;
  accent_color: string;
  logo_data_url: string | null;
  footer_text: string | null;
}

const MAX_LOGO = 300_000;

export function BrandingForm({ initial }: { initial: Branding }) {
  const router = useRouter();
  const [b, setB] = useState(initial);
  const [busy, setBusy] = useState(false);

  function pickLogo(file: File | undefined) {
    if (!file) return;
    if (!["image/png", "image/jpeg", "image/webp"].includes(file.type)) return toast.error("Use a PNG, JPEG or WebP logo");
    if (file.size > MAX_LOGO) return toast.error("Logo must be under 300 KB");
    const reader = new FileReader();
    reader.onload = () => setB((cur) => ({ ...cur, logo_data_url: String(reader.result) }));
    reader.readAsDataURL(file);
  }

  return (
    <form
      className="flex flex-col gap-4"
      onSubmit={async (e) => {
        e.preventDefault();
        setBusy(true);
        try {
          await api("/reports/branding", { method: "PUT", body: { ...b, agency_name: b.agency_name || null, footer_text: b.footer_text || null } });
          toast.success("Report branding saved");
          router.refresh();
        } catch (err) {
          toast.error("Couldn't save", { description: (err as Error).message });
        } finally {
          setBusy(false);
        }
      }}
    >
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="agency">Agency or company name</Label>
          <Input id="agency" value={b.agency_name ?? ""} onChange={(e) => setB({ ...b, agency_name: e.target.value })} placeholder="Shown in the report footer" />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="title">Report title</Label>
          <Input id="title" required value={b.report_title} onChange={(e) => setB({ ...b, report_title: e.target.value })} />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="primary">Title colour</Label>
          <div className="flex items-center gap-2">
            <input id="primary" type="color" value={b.primary_color} onChange={(e) => setB({ ...b, primary_color: e.target.value })} className="h-8 w-12 rounded border" />
            <span className="font-mono text-xs">{b.primary_color}</span>
          </div>
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="accent">Accent colour (bars, table headers)</Label>
          <div className="flex items-center gap-2">
            <input id="accent" type="color" value={b.accent_color} onChange={(e) => setB({ ...b, accent_color: e.target.value })} className="h-8 w-12 rounded border" />
            <span className="font-mono text-xs">{b.accent_color}</span>
          </div>
        </div>
        <div className="flex flex-col gap-1.5 sm:col-span-2">
          <Label htmlFor="footer">Footer text</Label>
          <Input id="footer" value={b.footer_text ?? ""} onChange={(e) => setB({ ...b, footer_text: e.target.value })} placeholder="e.g. Confidential: prepared for CeraVe" />
        </div>
        <div className="flex flex-col gap-1.5 sm:col-span-2">
          <Label>Logo (PNG, JPEG or WebP, under 300 KB)</Label>
          <div className="flex flex-wrap items-center gap-3">
            {b.logo_data_url ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={b.logo_data_url} alt="Report logo" className="h-10 max-w-40 rounded border object-contain p-1" />
            ) : (
              <span className="text-sm text-muted-foreground">No logo</span>
            )}
            <label className="inline-flex h-8 cursor-pointer items-center gap-1.5 rounded-lg border px-2.5 text-sm font-medium hover:bg-muted">
              <ImageUp className="size-4" /> Choose file
              <input type="file" accept="image/png,image/jpeg,image/webp" className="sr-only" onChange={(e) => pickLogo(e.target.files?.[0])} />
            </label>
            {b.logo_data_url && (
              <Button type="button" variant="ghost" size="sm" onClick={() => setB({ ...b, logo_data_url: null })}>
                <X /> Remove
              </Button>
            )}
          </div>
        </div>
      </div>
      <div className="flex items-center gap-3">
        <Button type="submit" disabled={busy || !b.report_title.trim()}>
          <Save /> Save branding
        </Button>
        <span className="h-2 flex-1 rounded-full" style={{ background: b.accent_color }} aria-hidden />
      </div>
    </form>
  );
}
