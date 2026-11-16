"use client";

import { Trash2, Upload } from "lucide-react";
import { useRouter } from "next/navigation";
import { useRef, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";

/** Upload a file as the raw request body to `path` (?filename=...). */
export function LogUpload({ path, label, accept, hint }: { path: string; label: string; accept: string; hint: string }) {
  const router = useRouter();
  const input = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  return (
    <div className="flex flex-wrap items-center gap-3">
      <input
        ref={input}
        type="file"
        accept={accept}
        className="sr-only"
        aria-label={label}
        onChange={async (e) => {
          const file = e.target.files?.[0];
          e.target.value = "";
          if (!file) return;
          if (file.size > 50 * 1024 * 1024) {
            toast.error("File is larger than 50 MB", { description: "Split it or upload a shorter period." });
            return;
          }
          setBusy(true);
          try {
            const res = await fetch(`/api${path}?filename=${encodeURIComponent(file.name)}`, { method: "POST", body: file });
            const body = await res.json().catch(() => ({}));
            if (!res.ok) throw new Error(body.detail ?? `HTTP ${res.status}`);
            toast.success(`${file.name}: ${body.matched} matching rows from ${body.lines} lines`, body.skipped ? { description: `${body.skipped} lines could not be read` } : undefined);
            router.refresh();
          } catch (err) {
            toast.error("Upload failed", { description: (err as Error).message });
          } finally {
            setBusy(false);
          }
        }}
      />
      <Button disabled={busy} onClick={() => input.current?.click()}>
        <Upload /> {busy ? "Reading…" : label}
      </Button>
      <p className="text-xs text-muted-foreground">{hint}</p>
    </div>
  );
}

export function DeleteUpload({ path, name }: { path: string; name: string }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  return (
    <Button
      variant="ghost"
      size="icon-sm"
      aria-label={`Delete ${name}`}
      disabled={busy}
      onClick={async () => {
        if (!confirm(`Delete ${name} and its counts? This can't be undone.`)) return;
        setBusy(true);
        try {
          await api(path, { method: "DELETE" });
          toast.success("Deleted");
          router.refresh();
        } catch (e) {
          toast.error("Couldn't delete", { description: (e as Error).message });
        } finally {
          setBusy(false);
        }
      }}
    >
      <Trash2 />
    </Button>
  );
}
