"use client";

import { ExternalLink, MessageSquarePlus, Quote, RefreshCw } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { CarryLink, TimeAgo } from "@/components/common";
import { OwnerPicker } from "@/components/owner-picker";
import { runCheck } from "@/components/run-check-button";
import { SeverityBadge, StatusBadge, TruthBadge, VerdictBadge } from "@/components/status";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { ValueView } from "@/components/value-view";
import { useUrlState } from "@/hooks/use-url-state";
import { api } from "@/lib/api";
import { shortDate } from "@/lib/format";
import { ACTION_LABEL, describeEvent, explain, FIELD_LABEL, SOURCE_TYPE_LABEL, VERDICT_LABEL } from "@/lib/labels";
import type { AuditEvent, ConflictDetail, Status } from "@/lib/types";

export function ConflictSheet() {
  const { params, set } = useUrlState();
  const id = params.get("conflict");
  return (
    <Sheet open={!!id} onOpenChange={(open) => !open && set({ conflict: null })}>
      <SheetContent side="right" className="w-full gap-0 overflow-y-auto p-0 data-[side=right]:sm:max-w-xl">
        {id && <ConflictPanel key={id} id={Number(id)} />}
      </SheetContent>
    </Sheet>
  );
}

function ConflictPanel({ id }: { id: number }) {
  const router = useRouter();
  const [detail, setDetail] = useState<ConflictDetail | null>(null);
  const [history, setHistory] = useState<AuditEvent[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [dismissing, setDismissing] = useState(false);
  const [reason, setReason] = useState("");
  const [note, setNote] = useState("");

  const [version, setVersion] = useState(0);
  const reload = useCallback(() => setVersion((v) => v + 1), []);

  useEffect(() => {
    let cancelled = false;
    Promise.all([api<ConflictDetail>(`/conflicts/${id}`), api<AuditEvent[]>(`/conflicts/${id}/history`)])
      .then(([d, h]) => {
        if (cancelled) return;
        setDetail(d);
        setHistory(h);
        setError(null);
      })
      .catch((e: Error) => !cancelled && setError(e.message));
    return () => {
      cancelled = true;
    };
  }, [id, version]);

  async function act(fn: () => Promise<unknown>, success?: string) {
    setBusy(true);
    try {
      await fn();
      if (success) toast.success(success);
      reload();
      router.refresh();
      return true;
    } catch (e) {
      toast.error("That didn't work", { description: (e as Error).message });
      return false;
    } finally {
      setBusy(false);
    }
  }

  const patch = (body: Record<string, unknown>, success?: string) =>
    act(() => api(`/conflicts/${id}`, { method: "PATCH", body }), success);

  if (error) {
    return (
      <div className="flex flex-col gap-3 p-6">
        <SheetTitle>Couldn&apos;t load this conflict</SheetTitle>
        <p className="text-sm text-muted-foreground">{error}</p>
        <Button variant="outline" onClick={reload} className="w-fit">
          Try again
        </Button>
      </div>
    );
  }
  if (!detail) {
    return (
      <div className="flex flex-col gap-4 p-6" aria-busy="true">
        <SheetTitle className="sr-only">Loading conflict</SheetTitle>
        <Skeleton className="h-6 w-2/3" />
        <Skeleton className="h-16 w-full" />
        <Skeleton className="h-40 w-full" />
      </div>
    );
  }

  const d = detail;
  const pv = (d.page_value ?? {}) as { not_in_truth?: string[]; not_on_page?: string[] };
  const transitions = d.allowed_transitions.filter((s) => s !== "dismissed");

  return (
    <>
      <SheetHeader className="gap-3 border-b p-6 pr-12">
        <div className="flex flex-wrap gap-1.5">
          <VerdictBadge verdict={d.verdict} />
          <SeverityBadge severity={d.severity} />
          <StatusBadge status={d.status} />
          {d.truth_source === "inferred" && <TruthBadge status="inferred" />}
        </div>
        <SheetTitle className="text-lg leading-snug">
          {VERDICT_LABEL[d.verdict]}: {FIELD_LABEL[d.field].toLowerCase()} on {d.page_label}
        </SheetTitle>
        <SheetDescription>
          <CarryLink href={`/products/${d.sku_id}`} className="font-medium text-foreground underline-offset-4 hover:underline">
            {d.sku_name}
          </CarryLink>{" "}
          · {d.brand_name} · found <TimeAgo iso={d.detected_at} />
        </SheetDescription>
      </SheetHeader>

      <div className="flex flex-col gap-6 p-6">
        <p className="text-sm leading-relaxed">{explain(d)}</p>

        <div className="grid gap-3 sm:grid-cols-2">
          <section className="flex flex-col gap-2 rounded-xl border p-3">
            <h3 className="text-xs font-medium text-muted-foreground">
              {d.truth_source === "inferred" ? "Inferred truth (unverified: no truth sheet yet)" : "Approved by the brand"}
            </h3>
            <ValueView
              value={d.truth_value}
              highlight={pv.not_on_page}
              tone="good"
              empty="Nothing approved for this"
            />
            {d.truth_evidence_url && (
              <a
                href={d.truth_evidence_url}
                target="_blank"
                rel="noreferrer"
                className="mt-auto inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
              >
                Source of truth <ExternalLink className="size-3" />
              </a>
            )}
          </section>
          <section className="flex flex-col gap-2 rounded-xl border p-3">
            <h3 className="text-xs font-medium text-muted-foreground">
              {d.page_label} shows <span className="font-normal">({SOURCE_TYPE_LABEL[d.source_type] ?? d.source_type})</span>
            </h3>
            <ValueView value={d.page_value} highlight={pv.not_in_truth} />
            <a
              href={d.page_url}
              target="_blank"
              rel="noreferrer"
              className="mt-auto inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
            >
              Open page <ExternalLink className="size-3" />
            </a>
          </section>
        </div>

        {d.quote && (
          <figure className="rounded-xl bg-muted/60 p-3">
            <figcaption className="mb-1.5 flex items-center gap-1.5 text-xs text-muted-foreground">
              <Quote className="size-3.5" /> Evidence from the page
              {d.page_fetched_at && <> · captured {shortDate(d.page_fetched_at)}</>}
            </figcaption>
            <blockquote className="text-sm leading-relaxed">{d.quote}</blockquote>
          </figure>
        )}

        <Separator />

        <section className="flex flex-col gap-3">
          <h3 className="text-sm font-medium">Actions</h3>
          <div className="flex flex-wrap gap-2">
            {transitions.map((s: Status, i) => (
              <Button
                key={s}
                variant={i === 0 ? "default" : "outline"}
                disabled={busy}
                onClick={() => patch({ status: s }, s === "accepted" ? "Accepted. It's now a task on the fix board." : `Moved to "${ACTION_LABEL[s]}"`)}
              >
                {s === "accepted" ? "Accept (create fix task)" : ACTION_LABEL[s]}
              </Button>
            ))}
            {d.allowed_transitions.includes("dismissed") && !dismissing && (
              <Button variant="outline" disabled={busy} onClick={() => setDismissing(true)}>
                Dismiss
              </Button>
            )}
            <Button
              variant="ghost"
              disabled={busy}
              onClick={() => act(() => runCheck(d.sku_id))}
              title="Compare the latest stored page data with the approved claims again"
            >
              <RefreshCw /> Re-check
            </Button>
          </div>
          {dismissing && (
            <div className="flex flex-col gap-2 rounded-xl border p-3">
              <Label htmlFor="dismiss-reason">Why dismiss this? (required)</Label>
              <Textarea
                id="dismiss-reason"
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                placeholder="e.g. Same meaning; legal has approved this wording"
              />
              <div className="flex gap-2">
                <Button
                  variant="destructive"
                  disabled={busy || !reason.trim()}
                  onClick={async () => {
                    if (await patch({ status: "dismissed", reason }, "Dismissed")) setDismissing(false);
                  }}
                >
                  Dismiss conflict
                </Button>
                <Button variant="ghost" onClick={() => setDismissing(false)}>
                  Cancel
                </Button>
              </div>
            </div>
          )}
          {d.status === "dismissed" && d.dismiss_reason && (
            <p className="text-sm text-muted-foreground">Dismissed: {d.dismiss_reason}</p>
          )}
          {d.status === "verified" && (
            <p className="text-sm text-muted-foreground">Verified. Nothing left to do here.</p>
          )}

          <div className="grid gap-3 sm:grid-cols-2">
            <div className="flex flex-col gap-1.5">
              <Label>Owner</Label>
              <OwnerPicker value={d.owner} disabled={busy} onChange={(owner) => patch({ owner }, owner ? `Assigned to ${owner}` : "Owner removed")} />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="due-date">Due date</Label>
              <Input
                id="due-date"
                type="date"
                defaultValue={d.due_date ?? ""}
                disabled={busy}
                onChange={(e) => patch({ due_date: e.target.value || null }, "Due date saved")}
              />
            </div>
          </div>
        </section>

        <Separator />

        <section className="flex flex-col gap-3">
          <h3 className="text-sm font-medium">Notes & history</h3>
          <form
            className="flex flex-col gap-2"
            onSubmit={async (e) => {
              e.preventDefault();
              if (await act(() => api(`/conflicts/${id}/notes`, { method: "POST", body: { text: note } }), "Note added"))
                setNote("");
            }}
          >
            <Textarea
              aria-label="Add a note"
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="Add a note for the team…"
            />
            <Button type="submit" variant="outline" size="sm" disabled={busy || !note.trim()} className="w-fit">
              <MessageSquarePlus /> Add note
            </Button>
          </form>
          <ol className="flex flex-col gap-3 border-l pl-4">
            {[...history].reverse().map((e) => (
              <li key={e.id} className="relative text-sm">
                <span className="absolute top-1.5 -left-[21px] size-2 rounded-full bg-border ring-4 ring-background" />
                <span className="font-medium">{e.actor === "system" ? "Automatic check" : e.actor}</span>{" "}
                <span className="text-muted-foreground">{describeEvent(e.action, e.detail)}</span>
                <div className="text-xs text-muted-foreground">
                  <TimeAgo iso={e.at} />
                </div>
              </li>
            ))}
          </ol>
        </section>

        <Link
          href={`/products/${d.sku_id}`}
          className="text-sm text-muted-foreground underline-offset-4 hover:text-foreground hover:underline"
        >
          See every claim for this product →
        </Link>
      </div>
    </>
  );
}
