"use client";

import { Trash2, UserPlus } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api } from "@/lib/api";
import { invalidateTeam, type Member, type Role, type Team } from "@/lib/team";
import type { Brand } from "@/lib/types";

const ALL = "all";

function RolePicker({ roles, value, onChange, label }: { roles: Team["roles"]; value: Role; onChange: (r: Role) => void; label: string }) {
  const items = Object.entries(roles).map(([v, l]) => ({ value: v, label: l }));
  return (
    <Select items={items} value={value} onValueChange={(v) => onChange(v as Role)}>
      <SelectTrigger aria-label={label} className="w-40">
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
  );
}

function BrandScope({ brands, value, onChange, label }: { brands: Brand[]; value: number | null; onChange: (b: number | null) => void; label: string }) {
  const items = [{ value: ALL, label: "All brands" }, ...brands.map((b) => ({ value: String(b.id), label: b.name }))];
  return (
    <Select items={items} value={value === null ? ALL : String(value)} onValueChange={(v) => onChange(v === ALL ? null : Number(v))}>
      <SelectTrigger aria-label={label} className="w-36">
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
  );
}

export function TeamManager({ team, brands }: { team: Team; brands: Brand[] }) {
  const router = useRouter();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<Role>("brand_manager");
  const [brand, setBrand] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);

  async function call(fn: () => Promise<unknown>, ok: string) {
    setBusy(true);
    try {
      await fn();
      invalidateTeam();
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

  const update = (m: Member, body: Record<string, unknown>) =>
    call(() => api(`/team/${m.id}`, { method: "PATCH", body }), `Updated ${m.name}`);

  return (
    <div className="flex flex-col gap-4">
      <form
        className="flex flex-wrap items-end gap-2"
        onSubmit={async (e) => {
          e.preventDefault();
          const ok = await call(
            () => api("/team", { method: "POST", body: { name, email: email || null, role, brand_id: brand } }),
            `Added ${name}`,
          );
          if (ok) {
            setName("");
            setEmail("");
          }
        }}
      >
        <Input aria-label="Name" placeholder="Name" value={name} onChange={(e) => setName(e.target.value)} className="w-48" />
        <Input aria-label="Email (optional)" type="email" placeholder="Email (optional)" value={email} onChange={(e) => setEmail(e.target.value)} className="w-56" />
        <RolePicker roles={team.roles} value={role} onChange={setRole} label="Role for new member" />
        <BrandScope brands={brands} value={brand} onChange={setBrand} label="Brand for new member" />
        <Button type="submit" disabled={busy || !name.trim()}>
          <UserPlus /> Add
        </Button>
      </form>

      <div className="overflow-x-auto rounded-xl border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Name</TableHead>
              <TableHead>Role</TableHead>
              <TableHead>Brand</TableHead>
              <TableHead className="w-0" />
            </TableRow>
          </TableHeader>
          <TableBody>
            {team.members.map((m) => (
              <TableRow key={m.id}>
                <TableCell>
                  <div className="font-medium">{m.name}</div>
                  <div className="text-xs text-muted-foreground">{m.email ?? "No email"}</div>
                </TableCell>
                <TableCell>
                  <RolePicker roles={team.roles} value={m.role} onChange={(r) => update(m, { role: r })} label={`Role for ${m.name}`} />
                </TableCell>
                <TableCell>
                  <BrandScope brands={brands} value={m.brand_id} onChange={(b) => update(m, { brand_id: b })} label={`Brand for ${m.name}`} />
                </TableCell>
                <TableCell>
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    aria-label={`Remove ${m.name}`}
                    disabled={busy}
                    onClick={() => call(() => api(`/team/${m.id}`, { method: "DELETE" }), `Removed ${m.name}`)}
                  >
                    <Trash2 />
                  </Button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
