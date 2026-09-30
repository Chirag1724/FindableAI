import type { ScanStatus, EntailmentStatus } from "@/types/scan";

// Numeric formatters

export function formatScore(score: number): string {
  return score.toFixed(1);
}

export function formatPercent(value: number, decimals = 1): string {
  return `${value.toFixed(decimals)}%`;
}

export function formatDuration(seconds: number): string {
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  const m = Math.floor(seconds / 60);
  const s = Math.round(seconds % 60);
  return `${m}m ${s}s`;
}

export function formatRelativeTime(isoString: string): string {
  const date = new Date(isoString);
  if (isNaN(date.getTime())) return isoString;
  const diffMs = Date.now() - date.getTime();
  const diffSec = Math.floor(diffMs / 1000);
  if (diffSec < 5) return "just now";
  if (diffSec < 60) return `${diffSec}s ago`;
  const diffMin = Math.floor(diffSec / 60);
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffHr = Math.floor(diffMin / 60);
  if (diffHr < 24) return `${diffHr}h ago`;
  return date.toLocaleDateString();
}

export function truncate(str: string, max: number): string {
  if (str.length <= max) return str;
  return str.slice(0, max - 1) + "\u2026";
}

// Grade color - returns a Tailwind text class

export function gradeColor(grade: string): string {
  switch (grade.toUpperCase()) {
    case "S":
      return "text-amber-300 font-extrabold";
    case "A":
    case "A+":
      return "text-emerald-400";
    case "A-":
    case "B+":
    case "B":
      return "text-violet-400";
    case "B-":
    case "C+":
    case "C":
      return "text-sky-400";
    case "C-":
    case "D+":
    case "D":
      return "text-amber-400";
    default:
      return "text-rose-400";
  }
}

// Status meta - returns display metadata for scan and intent statuses

export interface StatusMeta {
  label: string;
  /** Lucide icon name (verified to exist in 0.395.x) */
  iconName: string;
  /** Tailwind color classes for text + background badge */
  classes: string;
  /** Dot/ring color for indicators */
  dotClass: string;
}

/** Maps ScanStatus to display metadata. */
export function scanStatusMeta(status: ScanStatus): StatusMeta {
  switch (status) {
    case "pending":
      return {
        label: "Pending",
        iconName: "clock",
        classes: "bg-zinc-800 text-zinc-300",
        dotClass: "bg-zinc-400",
      };
    case "crawling":
      return {
        label: "Crawling",
        iconName: "globe",
        classes: "bg-sky-950 text-sky-300",
        dotClass: "bg-sky-400",
      };
    case "extracting_dom":
      return {
        label: "Extracting DOM",
        iconName: "layers",
        classes: "bg-sky-950 text-sky-300",
        dotClass: "bg-sky-400",
      };
    case "synthesizing_intents":
      return {
        label: "Synthesizing Intents",
        iconName: "cpu",
        classes: "bg-violet-950 text-violet-300",
        dotClass: "bg-violet-400",
      };
    case "hybrid_retrieval":
      return {
        label: "Hybrid Retrieval",
        iconName: "search",
        classes: "bg-violet-950 text-violet-300",
        dotClass: "bg-violet-400",
      };
    case "nli_evaluation":
      return {
        label: "NLI Evaluation",
        iconName: "activity",
        classes: "bg-amber-950 text-amber-300",
        dotClass: "bg-amber-400",
      };
    case "computing_fscore":
      return {
        label: "Computing F-Score",
        iconName: "bar-chart-2",
        classes: "bg-amber-950 text-amber-300",
        dotClass: "bg-amber-400",
      };
    case "generating_patches":
      return {
        label: "Generating Patches",
        iconName: "git-pull-request",
        classes: "bg-emerald-950 text-emerald-300",
        dotClass: "bg-emerald-400",
      };
    case "completed":
      return {
        label: "Completed",
        iconName: "check-circle",
        classes: "bg-emerald-950 text-emerald-300",
        dotClass: "bg-emerald-400",
      };
    case "failed":
      return {
        label: "Failed",
        iconName: "alert-triangle",
        classes: "bg-rose-950 text-rose-300",
        dotClass: "bg-rose-400",
      };
  }
}

/** Maps EntailmentStatus to display metadata. */
export function entailmentStatusMeta(status: EntailmentStatus): StatusMeta {
  switch (status) {
    case "SUPPORTED":
      return {
        label: "Supported",
        iconName: "check-circle",
        classes: "bg-emerald-950 text-emerald-300",
        dotClass: "bg-emerald-400",
      };
    case "PARTIALLY_SUPPORTED":
      return {
        label: "Partial",
        iconName: "minus-circle",
        classes: "bg-sky-950 text-sky-300",
        dotClass: "bg-sky-400",
      };
    case "CONTRADICTED":
      return {
        label: "Contradicted",
        iconName: "alert-triangle",
        classes: "bg-rose-950 text-rose-300",
        dotClass: "bg-rose-400",
      };
    case "UNKNOWN":
      return {
        label: "Unknown",
        iconName: "help-circle",
        classes: "bg-amber-950 text-amber-300",
        dotClass: "bg-amber-400",
      };
  }
}