import {
  Bell,
  Bot,
  FileText,
  Globe,
  LayoutDashboard,
  Lightbulb,
  ListChecks,
  Package,
  Scale,
  Settings,
  ShieldCheck,
  SquareKanban,
} from "lucide-react";

export const NAV = [
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
      { href: "/ai-visibility", label: "AI visibility", icon: Bot },
      { href: "/audit", label: "Site & entity audit", icon: Globe },
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
] as const;

export const RANGES = [
  { value: "4w", label: "Last 4 weeks" },
  { value: "12w", label: "Last 12 weeks" },
  { value: "26w", label: "Last 6 months" },
  { value: "52w", label: "Last 12 months" },
] as const;
export const DEFAULT_RANGE = "12w";
