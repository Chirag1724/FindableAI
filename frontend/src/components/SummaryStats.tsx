"use client";

import type { AuditSummary } from "@/types/scan";
import { useCountUp } from "@/hooks/useCountUp";
import { formatDuration } from "@/lib/format";
import { Globe, Layers, Compass, AlertTriangle, Clock } from "lucide-react";

interface StatCardProps {
  label: string;
  value: number;
  icon: React.ElementType;
  iconColor: string;
  suffix?: string;
  decimals?: number;
  isDuration?: boolean;
  className?: string;
}

function StatCard({
  label,
  value,
  icon: Icon,
  iconColor,
  suffix = "",
  decimals = 0,
  isDuration = false,
  className = "",
}: StatCardProps) {
  const { value: animatedValue, ref } = useCountUp(value, isDuration ? 1 : decimals);

  return (
    <div
      className={`group relative overflow-hidden rounded-xl bg-surface/90 backdrop-blur-md p-4 sm:p-5 shadow-border transition-all duration-200 hover:border-white/[0.14] hover:bg-surface-secondary/70 ${className}`}
    >
      <div className="flex items-center justify-between gap-2 mb-2">
        <span className="text-[11px] font-semibold uppercase tracking-wider text-text-muted">
          {label}
        </span>
        <div className={`flex h-6 w-6 items-center justify-center rounded-md bg-white/[0.03] border border-white/[0.06] ${iconColor}`}>
          <Icon size={12} aria-hidden="true" />
        </div>
      </div>
      <p className="text-2xl sm:text-3xl font-bold font-mono tracking-tight text-white tabular-nums">
        <span ref={ref}>
          {isDuration ? formatDuration(value) : `${animatedValue}${suffix}`}
        </span>
      </p>
    </div>
  );
}

export function SummaryStats({ summary }: { summary: AuditSummary }) {
  return (
    <div className="grid grid-cols-2 gap-3 sm:gap-4 sm:grid-cols-3 lg:grid-cols-5">
      <StatCard
        label="Pages Crawled"
        value={summary.pages_crawled}
        icon={Globe}
        iconColor="text-sky-400"
      />
      <StatCard
        label="DOM Chunks"
        value={summary.dom_chunks_extracted}
        icon={Layers}
        iconColor="text-violet-400"
      />
      <StatCard
        label="Intents Tested"
        value={summary.intents_generated}
        icon={Compass}
        iconColor="text-emerald-400"
      />
      <StatCard
        label="Contradictions"
        value={summary.contradictions_detected}
        icon={AlertTriangle}
        iconColor={summary.contradictions_detected > 0 ? "text-rose-400" : "text-emerald-400"}
      />
      <StatCard
        label="Scan Duration"
        value={summary.execution_time_seconds}
        icon={Clock}
        iconColor="text-amber-400"
        isDuration
        className="col-span-2 sm:col-span-1"
      />
    </div>
  );
}