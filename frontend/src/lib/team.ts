"use client";

import { useEffect, useState } from "react";
import { api } from "./api";

export type Role = "cmo" | "brand_manager" | "ecommerce" | "agency" | "regulatory";

export interface Member {
  id: number;
  name: string;
  email: string | null;
  role: Role;
  role_label: string;
  brand_id: number | null;
  brand_name: string | null;
}

export interface Team {
  roles: Record<Role, string>;
  owner_type_role: Record<string, Role>;
  members: Member[];
}

let cache: Promise<Team> | null = null;

/** Team list for owner dropdowns, fetched once per page load. */
export function useTeam(): Team | null {
  const [team, setTeam] = useState<Team | null>(null);
  useEffect(() => {
    let cancelled = false;
    cache ??= api<Team>("/team");
    cache
      .then((t) => !cancelled && setTeam(t))
      .catch(() => {
        cache = null;
      });
    return () => {
      cancelled = true;
    };
  }, []);
  return team;
}

export function invalidateTeam() {
  cache = null;
}
