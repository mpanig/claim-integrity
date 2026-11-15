"use client";

import { ListPlus } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";
import { OwnerPicker } from "@/components/owner-picker";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api } from "@/lib/api";
import type { Role } from "@/lib/team";

export function CreateTaskDialog({
  title,
  conflictIds,
  ownerHint,
  suggestRole,
}: {
  title: string;
  conflictIds: number[];
  ownerHint: string;
  suggestRole?: Role;
}) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [owner, setOwner] = useState<string | null>(null);
  const [due, setDue] = useState("");
  const [busy, setBusy] = useState(false);

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger render={<Button size="sm" />}>
        <ListPlus /> Create task
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Create task</DialogTitle>
          <DialogDescription>
            “{title}”. This accepts the {conflictIds.length} related issue{conflictIds.length === 1 ? "" : "s"} and puts
            them on the fix board. Suggested owner: {ownerHint}.
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="flex flex-col gap-1.5">
            <Label>Owner</Label>
            <OwnerPicker value={owner} onChange={setOwner} suggestRole={suggestRole} />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="task-due">Due date</Label>
            <Input id="task-due" type="date" value={due} onChange={(e) => setDue(e.target.value)} />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => setOpen(false)}>
            Cancel
          </Button>
          <Button
            disabled={busy}
            onClick={async () => {
              setBusy(true);
              try {
                const r = await api<{ accepted: number }>("/recommendations/task", {
                  method: "POST",
                  body: { title, conflict_ids: conflictIds, owner, due_date: due || null },
                });
                toast.success("Task created", { description: `${r.accepted} issue${r.accepted === 1 ? "" : "s"} moved to the fix board.` });
                setOpen(false);
                router.refresh();
              } catch (e) {
                toast.error("Couldn't create the task", { description: (e as Error).message });
              } finally {
                setBusy(false);
              }
            }}
          >
            Create task
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
