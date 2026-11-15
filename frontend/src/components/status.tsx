import { CircleAlert, CircleCheck, CircleDashed, CircleMinus, OctagonAlert, TriangleAlert } from "lucide-react";
import { cn } from "@/lib/utils";
import { scoreTone, severityTier, STATUS_LABEL, VERDICT_LABEL, VERDICT_TONE } from "@/lib/labels";
import type { Status, Verdict } from "@/lib/types";

type Tone = "good" | "warning" | "serious" | "critical" | "neutral";

const TONE_BG: Record<Tone, string> = {
  good: "bg-good/12 ring-good/30",
  warning: "bg-warning/15 ring-warning/40",
  serious: "bg-serious/15 ring-serious/40",
  critical: "bg-critical/12 ring-critical/30",
  neutral: "bg-muted ring-border",
};
const TONE_ICON: Record<Tone, string> = {
  good: "text-good",
  warning: "text-warning",
  serious: "text-serious",
  critical: "text-critical",
  neutral: "text-muted-foreground",
};

/** A status pill: tinted background, coloured icon, text in normal ink (never colour alone). */
export function Pill({
  tone,
  icon: Icon,
  children,
  className,
  title,
}: {
  tone: Tone;
  icon?: React.ComponentType<{ className?: string }>;
  children: React.ReactNode;
  className?: string;
  title?: string;
}) {
  return (
    <span
      title={title}
      className={cn(
        "inline-flex h-6 shrink-0 items-center gap-1.5 rounded-full px-2 text-xs font-medium text-foreground ring-1 ring-inset whitespace-nowrap",
        TONE_BG[tone],
        className,
      )}
    >
      {Icon && <Icon className={cn("size-3.5", TONE_ICON[tone])} />}
      {children}
    </span>
  );
}

export function VerdictBadge({ verdict, className, label }: { verdict: Verdict; className?: string; label?: string }) {
  const tone = VERDICT_TONE[verdict];
  return (
    <Pill tone={tone} icon={tone === "critical" ? OctagonAlert : TriangleAlert} className={className}>
      {label ?? VERDICT_LABEL[verdict]}
    </Pill>
  );
}

export function SeverityBadge({ severity }: { severity: number }) {
  const tier = severityTier(severity);
  return (
    <Pill tone={tier.tone} icon={tier.tone === "critical" ? OctagonAlert : CircleAlert} title={`Severity ${severity} of 10`}>
      {tier.label}
    </Pill>
  );
}

const STATUS_TONE: Record<Status, Tone> = {
  open: "neutral",
  accepted: "serious",
  fixed: "warning",
  verified: "good",
  dismissed: "neutral",
};
const STATUS_ICON: Record<Status, React.ComponentType<{ className?: string }>> = {
  open: CircleDashed,
  accepted: CircleAlert,
  fixed: CircleCheck,
  verified: CircleCheck,
  dismissed: CircleMinus,
};

export function StatusBadge({ status }: { status: Status }) {
  return (
    <Pill tone={STATUS_TONE[status]} icon={STATUS_ICON[status]}>
      {STATUS_LABEL[status]}
    </Pill>
  );
}

const SCORE_LABEL = { good: "Consistent", warning: "Needs attention", critical: "At risk", none: "Not checked" } as const;

export function ScoreBadge({ score, className }: { score: number | null; className?: string }) {
  const tone = scoreTone(score);
  const icon = tone === "good" ? CircleCheck : tone === "warning" ? TriangleAlert : tone === "critical" ? OctagonAlert : CircleDashed;
  return (
    <Pill tone={tone === "none" ? "neutral" : tone} icon={icon} className={className} title={SCORE_LABEL[tone]}>
      <span className="tabular-nums">{score ?? "–"}</span>
      <span className="text-muted-foreground">{SCORE_LABEL[tone]}</span>
    </Pill>
  );
}

/** Hero figure for a consistency score with a thin progress track. */
export function ScoreHero({ score, label }: { score: number | null; label: string }) {
  const tone = scoreTone(score);
  const bar = { good: "bg-good", warning: "bg-warning", critical: "bg-critical", none: "bg-muted" }[tone];
  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-baseline gap-2">
        <span className="text-4xl font-semibold tracking-tight">{score ?? "–"}</span>
        <span className="text-sm text-muted-foreground">/ 100</span>
      </div>
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted" role="presentation">
        <div className={cn("h-full rounded-full", bar)} style={{ width: `${score ?? 0}%` }} />
      </div>
      <span className="text-xs text-muted-foreground">
        {label} · {SCORE_LABEL[tone]}
      </span>
    </div>
  );
}
