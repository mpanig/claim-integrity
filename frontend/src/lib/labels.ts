/** Plain-language wording for everything the backend returns as enums. */
import type { Conflict, Field, Status, Verdict } from "./types";

export const VERDICT_LABEL: Record<Verdict, string> = {
  contradiction: "Contradicts itself",
  risky: "Unapproved claim",
  outdated: "Outdated info on retailer",
  weaker: "Approved claim missing",
  missing: "Information missing",
  drift: "Wording differs",
};

export const VERDICT_HINT: Record<Verdict, string> = {
  contradiction: "The page makes a claim its own ingredient list disproves.",
  risky: "The page shows a claim the brand has not approved.",
  outdated: "The page shows an older formula or ingredient list.",
  weaker: "The page leaves out a claim the brand approved.",
  missing: "The page shows nothing for this information.",
  drift: "Same meaning, different words, names or order.",
};

export const VERDICT_ORDER: Verdict[] = ["contradiction", "risky", "outdated", "weaker", "missing", "drift"];

/** Red = could mislead shoppers or create legal risk. Amber = inconsistent but lower risk. */
export const VERDICT_TONE: Record<Verdict, "critical" | "warning"> = {
  contradiction: "critical",
  risky: "critical",
  outdated: "critical",
  weaker: "warning",
  missing: "warning",
  drift: "warning",
};

export const FIELD_LABEL: Record<Field, string> = {
  name: "Product name",
  ingredients: "Ingredient list",
  free_from: "Free-from claims",
  claims: "Product claims",
  seals: "Seals & endorsements",
};

export const STATUS_LABEL: Record<Status, string> = {
  open: "To review",
  accepted: "Accepted · to fix",
  fixed: "Fixed · awaiting check",
  verified: "Verified",
  dismissed: "Dismissed",
};

export const ACTION_LABEL: Record<Status, string> = {
  open: "Reopen",
  accepted: "Accept",
  fixed: "Mark fixed",
  verified: "Mark verified",
  dismissed: "Dismiss",
};

export const SOURCE_TYPE_LABEL: Record<string, string> = {
  retailer: "Retailer",
  professional: "Professional site",
  brand: "Brand site",
};

export function severityTier(severity: number): { label: string; tone: "critical" | "serious" | "warning" } {
  if (severity >= 9) return { label: "High risk", tone: "critical" };
  if (severity >= 4) return { label: "Medium", tone: "serious" };
  return { label: "Low", tone: "warning" };
}

export function scoreTone(score: number | null): "good" | "warning" | "critical" | "none" {
  if (score === null) return "none";
  if (score >= 80) return "good";
  if (score >= 50) return "warning";
  return "critical";
}

function list(items: unknown): string {
  if (!Array.isArray(items) || items.length === 0) return "";
  const words = items.map(String);
  if (words.length === 1) return words[0];
  return `${words.slice(0, -1).join(", ")} and ${words[words.length - 1]}`;
}

function show(value: unknown): string {
  if (value === null || value === undefined) return "nothing";
  if (Array.isArray(value)) return list(value);
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

/** One or two sentences a CMO can read without knowing the rules. */
export function explain(c: Pick<Conflict, "verdict" | "field" | "page_label" | "page_value" | "truth_value">): string {
  const where = c.page_label;
  const field = FIELD_LABEL[c.field].toLowerCase();
  switch (c.verdict) {
    case "outdated": {
      const pv = (c.page_value ?? {}) as { not_in_truth?: string[]; not_on_page?: string[] };
      const extra = pv.not_in_truth?.length ? ` It lists ${list(pv.not_in_truth)}, which are not in the current formula` : "";
      const gone = pv.not_on_page?.length ? `${extra ? ", and" : " It"} leaves out ${list(pv.not_on_page)}` : "";
      return `${where} shows an older ingredient list.${extra}${gone}. Shoppers checking ingredients see the wrong formula.`;
    }
    case "contradiction": {
      const pv = (c.page_value ?? {}) as { claim?: string; ingredients?: string[] };
      return `${where} says "${pv.claim}", but its own ingredient list contains ${list(pv.ingredients)}. This is a misleading claim.`;
    }
    case "risky":
      return `${where} shows "${show(c.page_value)}", which is not an approved claim for this product. Unapproved claims can create legal and regulatory risk.`;
    case "weaker":
      return `${where} does not show the approved claim "${show(c.truth_value)}". Shoppers there miss a reason to buy.`;
    case "missing":
      return `${where} shows no ${field}. The approved version is: ${show(c.truth_value)}.`;
    case "drift":
      if (c.field === "ingredients")
        return `${where} lists the same ingredients, but with older ingredient names or in a different order.`;
      if (c.field === "name") return `${where} calls the product "${show(c.page_value)}" instead of "${show(c.truth_value)}".`;
      return `${where} says "${show(c.page_value)}" where the approved wording is "${show(c.truth_value)}". Same meaning, inconsistent wording.`;
  }
}

/** What happened in an audit event, as a short phrase. */
export function describeEvent(action: string, detail: Record<string, unknown>): string {
  switch (action) {
    case "detected":
      return "found this issue";
    case "status": {
      const to = detail.to as Status;
      const reason = detail.reason ? ` (${detail.reason})` : "";
      return `moved it to ${STATUS_LABEL[to] ?? to}${reason}`;
    }
    case "assigned":
      return detail.owner ? `assigned it to ${detail.owner}` : "removed the owner";
    case "due_date":
      return detail.due_date ? `set the due date to ${detail.due_date}` : "cleared the due date";
    case "note":
      return `added a note: "${detail.text}"`;
    case "check_run":
      return `ran a check: ${detail.new ?? 0} new, ${detail.resolved ?? 0} resolved, ${detail.reopened ?? 0} reopened`;
    case "claim_approved":
      return `approved new ${FIELD_LABEL[detail.field as Field]?.toLowerCase() ?? detail.field}`;
    case "claim_removed":
      return `removed the approved ${FIELD_LABEL[detail.field as Field]?.toLowerCase() ?? detail.field}`;
    case "sku_created":
      return "added the product";
    case "sku_updated":
      return "edited product details";
    default:
      return action.replaceAll("_", " ");
  }
}

/** A few words naming the specific claim at issue, for lists and cards. */
export function snippet(c: Pick<Conflict, "verdict" | "field" | "page_value" | "truth_value">): string {
  switch (c.verdict) {
    case "outdated": {
      const pv = (c.page_value ?? {}) as { not_in_truth?: string[]; not_on_page?: string[] };
      return `${pv.not_in_truth?.length ?? 0} extra, ${pv.not_on_page?.length ?? 0} missing ingredients`;
    }
    case "contradiction":
      return `“${(c.page_value as { claim?: string })?.claim ?? ""}”`;
    case "risky":
      return `“${show(c.page_value)}”`;
    case "weaker":
      return `Missing “${show(c.truth_value)}”`;
    case "missing":
      return "Nothing shown";
    case "drift":
      return c.field === "ingredients" ? "Older names or order" : `“${show(c.page_value)}” vs “${show(c.truth_value)}”`;
  }
}
