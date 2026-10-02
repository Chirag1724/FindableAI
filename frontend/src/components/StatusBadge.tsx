import type { EntailmentStatus, ContradictionSeverity } from "@/types/scan";
import {
  CheckCircle, MinusCircle, AlertTriangle, HelpCircle,
} from "lucide-react";

interface StatusBadgeProps {
  status: EntailmentStatus | ContradictionSeverity;
  className?: string;
}

interface BadgeMeta {
  label: string;
  icon: React.ReactNode;
  classes: string;
}

function getMeta(status: EntailmentStatus | ContradictionSeverity): BadgeMeta {
  switch (status) {
    case "SUPPORTED":
      return {
        label: "Supported",
        icon: <CheckCircle size={11} aria-hidden="true" />,
        classes: "bg-emerald-950/60 text-emerald-300 ring-1 ring-inset ring-emerald-800",
      };
    case "PARTIALLY_SUPPORTED":
      return {
        label: "Partial",
        icon: <MinusCircle size={11} aria-hidden="true" />,
        classes: "bg-sky-950/60 text-sky-300 ring-1 ring-inset ring-sky-800",
      };
    case "CONTRADICTED":
      return {
        label: "Contradicted",
        icon: <AlertTriangle size={11} aria-hidden="true" />,
        classes: "bg-rose-950/60 text-rose-300 ring-1 ring-inset ring-rose-800",
      };
    case "UNKNOWN":
      return {
        label: "Unknown",
        icon: <HelpCircle size={11} aria-hidden="true" />,
        classes: "bg-amber-950/60 text-amber-300 ring-1 ring-inset ring-amber-800",
      };
    case "HARD_CONTRADICTION":
      return {
        label: "Hard Contradiction",
        icon: <AlertTriangle size={11} aria-hidden="true" />,
        classes: "bg-rose-950/60 text-rose-300 ring-1 ring-inset ring-rose-800",
      };
    case "SOFT_INCONSISTENCY":
      return {
        label: "Soft Inconsistency",
        icon: <MinusCircle size={11} aria-hidden="true" />,
        classes: "bg-amber-950/60 text-amber-300 ring-1 ring-inset ring-amber-800",
      };
  }
}

export function StatusBadge({ status, className = "" }: StatusBadgeProps) {
  const meta = getMeta(status);
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ${meta.classes} ${className}`}
    >
      {meta.icon}
      {meta.label}
    </span>
  );
}