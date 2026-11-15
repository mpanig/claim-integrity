import type { Status } from "./types";

/** Mirrors backend app/services/workflow.py TRANSITIONS (the backend enforces it). */
export const TRANSITIONS: Record<Status, Status[]> = {
  open: ["accepted", "dismissed"],
  accepted: ["fixed"],
  fixed: ["verified", "open"],
  verified: [],
  dismissed: [],
};

export function canMove(from: Status, to: Status): boolean {
  return TRANSITIONS[from].includes(to);
}
