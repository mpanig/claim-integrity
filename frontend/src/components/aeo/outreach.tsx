"use client";

import { CalendarClock, ExternalLink, Plus, Trash2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";
import { DemoBadge } from "@/components/common";
import { Pill } from "@/components/status";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { api } from "@/lib/api";

export interface OutreachData {
  demo: boolean;
  statuses: { key: string; label: string; count: number }[];
  rows: {
    id: number;
    domain: string;
    page_url: string | null;
    status: string;
    owner_id: number | null;
    owner: string | null;
    note: string | null;
    due_date: string | null;
    published_url: string | null;
    gap_citations: number;
    gap_now: number | null;
    citations_now: number | null;
    is_demo: boolean;
    overdue: boolean;
  }[];
  suggestions: { domain: string; page_type: string; gap: number; citations: number }[];
  owners: { id: number; name: string }[];
}

function useCall() {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const run = async (fn: () => Promise<unknown>, ok?: string) => {
    setBusy(true);
    try {
      await fn();
      if (ok) toast.success(ok);
      router.refresh();
    } catch (e) {
      toast.error("Couldn't save", { description: (e as Error).message });
    } finally {
      setBusy(false);
    }
  };
  return { busy, run };
}

/** Add a gap site (or any domain) to the tracker. */
export function AddOutreach({ domain, label = "Track" }: { domain?: string; label?: string }) {
  const { busy, run } = useCall();
  const [value, setValue] = useState("");
  if (domain)
    return (
      <Button size="sm" variant="outline" disabled={busy} onClick={() => run(() => api("/aeo/outreach", { method: "POST", body: { domain } }), `${domain} added to outreach`)}>
        <Plus /> {label}
      </Button>
    );
  return (
    <form
      className="flex gap-2"
      onSubmit={(e) => {
        e.preventDefault();
        if (value.trim().length >= 3) run(() => api("/aeo/outreach", { method: "POST", body: { domain: value.trim() } }), "Added").then(() => setValue(""));
      }}
    >
      <Input aria-label="Site to track" placeholder="site.com" value={value} onChange={(e) => setValue(e.target.value)} className="w-48" />
      <Button type="submit" size="sm" variant="outline" disabled={busy}>
        <Plus /> Add site
      </Button>
    </form>
  );
}

function Row({ r, data }: { r: OutreachData["rows"][number]; data: OutreachData }) {
  const { busy, run } = useCall();
  const patch = (body: Record<string, unknown>) => run(() => api(`/aeo/outreach/${r.id}`, { method: "PATCH", body }));
  const statusItems = data.statuses.map((s) => ({ value: s.key, label: s.label }));
  const ownerItems = [{ value: "none", label: "No owner" }, ...data.owners.map((o) => ({ value: String(o.id), label: o.name }))];
  return (
    <li className="flex flex-col gap-2 rounded-xl border p-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="font-medium">{r.domain}</p>
          <p className="text-xs text-muted-foreground">
            {r.gap_now ?? r.gap_citations} gap citations
            {r.citations_now !== null && ` of ${r.citations_now}`}
            {r.published_url && (
              <>
                {" · "}
                <a href={r.published_url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-0.5 hover:underline">
                  published <ExternalLink className="size-3" />
                </a>
              </>
            )}
          </p>
        </div>
        <div className="flex items-center gap-1">
          {r.is_demo && <DemoBadge />}
          {r.overdue && (
            <Pill tone="critical" icon={CalendarClock}>
              Overdue
            </Pill>
          )}
          {!r.is_demo && (
            <Button
              size="icon-sm"
              variant="ghost"
              aria-label={`Remove ${r.domain}`}
              disabled={busy}
              onClick={() => confirm(`Remove ${r.domain} from outreach?`) && run(() => api(`/aeo/outreach/${r.id}`, { method: "DELETE" }), "Removed")}
            >
              <Trash2 />
            </Button>
          )}
        </div>
      </div>
      {r.note && <p className="text-sm">{r.note}</p>}
      <div className="flex flex-wrap items-center gap-2">
        <Select items={statusItems} value={r.status} onValueChange={(v) => patch({ status: String(v) })} disabled={busy || r.is_demo}>
          <SelectTrigger size="sm" aria-label={`Status for ${r.domain}`} className="w-36">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {statusItems.map((s) => (
              <SelectItem key={s.value} value={s.value}>
                {s.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select items={ownerItems} value={r.owner_id ? String(r.owner_id) : "none"} onValueChange={(v) => patch({ owner_id: v === "none" ? null : Number(v) })} disabled={busy || r.is_demo}>
          <SelectTrigger size="sm" aria-label={`Owner for ${r.domain}`} className="w-44">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {ownerItems.map((o) => (
              <SelectItem key={o.value} value={o.value}>
                {o.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Input
          type="date"
          aria-label={`Due date for ${r.domain}`}
          className="h-8 w-40"
          defaultValue={r.due_date ?? ""}
          disabled={busy || r.is_demo}
          onBlur={(e) => e.target.value !== (r.due_date ?? "") && patch({ due_date: e.target.value || null })}
        />
      </div>
    </li>
  );
}

/** Columns by status; declined folded away. */
export function OutreachBoard({ data }: { data: OutreachData }) {
  const open = data.statuses.filter((s) => s.key !== "declined");
  const declined = data.rows.filter((r) => r.status === "declined");
  return (
    <div className="flex flex-col gap-4">
      <div className="grid gap-4 lg:grid-cols-3">
        {open.map((s) => (
          <section key={s.key} className="flex flex-col gap-2" aria-label={s.label}>
            <h3 className="flex items-center gap-2 text-sm font-medium">
              {s.label} <span className="text-muted-foreground tabular-nums">{s.count}</span>
            </h3>
            <ul className="flex flex-col gap-2">
              {data.rows
                .filter((r) => r.status === s.key)
                .map((r) => (
                  <Row key={r.id} r={r} data={data} />
                ))}
            </ul>
            {data.rows.every((r) => r.status !== s.key) && <p className="text-xs text-muted-foreground">Nothing here.</p>}
          </section>
        ))}
      </div>
      {declined.length > 0 && (
        <details>
          <summary className="cursor-pointer text-sm text-muted-foreground">Declined ({declined.length})</summary>
          <ul className="mt-2 grid gap-2 lg:grid-cols-3">
            {declined.map((r) => (
              <Row key={r.id} r={r} data={data} />
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}
