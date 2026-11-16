import {
  Bell,
  Bot,
  FileText,
  LayoutDashboard,
  Lightbulb,
  ListChecks,
  Package,
  Scale,
  Settings,
  ShieldCheck,
  SquareKanban,
  type LucideIcon,
} from "lucide-react";

export interface NavItem {
  href: string;
  label: string;
  icon: LucideIcon;
  /** Subsections, shown as a collapsible group. */
  children?: { href: string; label: string }[];
}

export const NAV: { section: string; items: NavItem[] }[] = [
  {
    section: "Monitor",
    items: [
      { href: "/", label: "Overview", icon: LayoutDashboard },
      { href: "/products", label: "Products", icon: Package },
      { href: "/conflicts", label: "Conflicts", icon: ListChecks },
      { href: "/board", label: "Fix board", icon: SquareKanban },
    ],
  },
  {
    section: "Insights",
    items: [
      { href: "/competitors", label: "Competitors", icon: Scale },
      {
        href: "/aeo",
        label: "AEO / GEO",
        icon: Bot,
        children: [
          { href: "/aeo", label: "Overview" },
          { href: "/aeo/prompts", label: "Prompts" },
          { href: "/aeo/answers", label: "Answers" },
          { href: "/aeo/citations", label: "Citations & sources" },
          { href: "/aeo/perception", label: "Brand perception" },
          { href: "/aeo/content", label: "Content & pages" },
          { href: "/aeo/crawlers", label: "Crawlers & traffic" },
          { href: "/aeo/coverage", label: "Coverage" },
        ],
      },
      { href: "/recommendations", label: "Recommendations", icon: Lightbulb },
      { href: "/alerts", label: "Alerts", icon: Bell },
      { href: "/reports", label: "Reports", icon: FileText },
    ],
  },
  {
    section: "Manage",
    items: [
      { href: "/truth-sheets", label: "Truth sheets", icon: ShieldCheck },
      { href: "/settings", label: "Settings", icon: Settings },
    ],
  },
];

export const RANGES = [
  { value: "4w", label: "Last 4 weeks" },
  { value: "12w", label: "Last 12 weeks" },
  { value: "26w", label: "Last 6 months" },
  { value: "52w", label: "Last 12 months" },
] as const;
export const DEFAULT_RANGE = "12w";
