export type Verdict = "contradiction" | "risky" | "outdated" | "weaker" | "missing" | "drift";
export type Status = "open" | "accepted" | "fixed" | "verified" | "dismissed";
export type Field = "name" | "ingredients" | "free_from" | "claims" | "seals";

export interface Brand {
  id: number;
  name: string;
  organisation_name?: string | null;
  /** Name, plus the organisation when another organisation has a brand with the same name. */
  label?: string | null;
}

export interface Sku {
  id: number;
  organisation_id: number;
  brand_id: number;
  brand_name: string;
  gtin: string | null;
  name: string;
  line: string | null;
  last_checked_at: string | null;
  /** Older consistency value (100 = no drift); use drift_score. */
  score: number | null;
  /** 0 = no drift; higher = pages drift further from the truth. */
  drift_score: number | null;
  unresolved: number;
  by_verdict: Record<Verdict, number>;
  pages: number;
  /** approved = truth sheet; inferred = provisional truth from the sources (unverified); none = nothing to compare. */
  truth_status: TruthStatus;
  inferred_method: "majority" | "claude" | null;
}

export type TruthStatus = "approved" | "inferred" | "none";

export interface Conflict {
  id: number;
  sku_id: number;
  sku_name: string;
  brand_id: number;
  brand_name: string;
  page_id: number;
  page_url: string;
  page_label: string;
  source_type: string;
  field: Field;
  page_value: unknown;
  truth_value: unknown;
  verdict: Verdict;
  severity: number;
  status: Status;
  owner: string | null;
  due_date: string | null;
  dismiss_reason: string | null;
  detected_at: string;
  status_changed_at: string | null;
  /** Whether this was judged against the approved truth sheet or an inferred, unverified truth. */
  truth_source: "approved" | "inferred";
}

export interface ConflictDetail extends Conflict {
  quote: string | null;
  truth_evidence_url: string | null;
  page_fetched_at: string | null;
  allowed_transitions: Status[];
}

export interface AuditEvent {
  id: number;
  sku_id: number;
  sku_name: string;
  conflict_id: number | null;
  actor: string;
  action: string;
  detail: Record<string, unknown>;
  at: string;
}

export interface Claim {
  field: Field;
  value: string | string[];
  evidence_url: string | null;
  approved_by: string | null;
  created_at: string;
}

export interface Trends {
  demo: boolean;
  weeks: {
    week: string;
    score: number | null;
    drift_score: number | null;
    unresolved: number | null;
    verified: number | null;
    fixed: number | null;
    mean_days_to_fix: number | null;
    brands: Record<string, number | null>;
    drift_brands: Record<string, number | null>;
  }[];
  brands: Brand[];
}

export interface Summary {
  overall: {
    score: number | null;
    drift_score: number | null;
    unresolved: number;
    by_verdict: Record<Verdict, number>;
    by_status: Record<Status, number>;
    skus: number;
    pages: number;
    mean_days_to_fix: number | null;
  };
  by_source: { page_id: number; label: string; unresolved: number }[];
  brands: { id: number; name: string; score: number | null; drift_score: number | null; unresolved: number; skus: number }[];
  top: Conflict[];
  activity: AuditEvent[];
}

export interface MatrixCell {
  value: unknown;
  quote: string | null;
  state: "match" | "warn" | "bad" | "na";
  conflicts: { id: number; verdict: Verdict; severity: number; status: Status }[];
}

export interface Matrix {
  sku: Sku;
  fields: Field[];
  list_fields: Field[];
  truth: {
    label: string;
    url: string | null;
    values: Record<Field, unknown>;
    status: TruthStatus;
    method: "majority" | "claude" | null;
    /** Inferred truth: share of page weight agreeing with each value. */
    agreement: Partial<Record<Field, number>>;
  };
  sources: {
    page_id: number;
    label: string;
    url: string;
    source_type: string;
    weight: number;
    fetched_at: string;
    cells: Record<Field, MatrixCell>;
  }[];
}

export interface RunResult {
  new: number;
  reopened: number;
  resolved: number;
  unresolved: number;
  score: number | null;
  drift_score: number | null;
  truth_status: TruthStatus;
}

export interface InferredTruth {
  status: TruthStatus;
  method: "majority" | "claude" | null;
  sources: number;
  fields: Partial<Record<Field, string | string[]>>;
  agreement: Partial<Record<Field, number>>;
}

/** One page of conflicts (GET /conflicts/page). */
export interface ConflictPage {
  total: number;
  limit: number;
  offset: number;
  items: Conflict[];
  owners: string[];
}
