export interface Recommendation {
  key: string;
  rule: string;
  title: string;
  why: string;
  owner_type: "brand_web" | "ecommerce" | "pr_editorial" | "regulatory";
  owner_label: string;
  ease: number;
  severity: number;
  priority: number;
  impact_points: number;
  sku_id: number;
  sku_name: string;
  brand_name: string;
  pages: string[];
  conflict_ids: number[];
  state: "todo" | "in_progress";
  link: string | null;
  is_demo: boolean;
}

export interface Recommendations {
  owner_types: Record<Recommendation["owner_type"], string>;
  items: Recommendation[];
}

export function easeLabel(ease: number): string {
  if (ease >= 0.85) return "Quick win";
  if (ease >= 0.65) return "Moderate effort";
  return "Needs review";
}
